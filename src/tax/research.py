"""Deep Tax Research and the validation retry: the RQ2 harnesses on the teammate's tax RAG.

Protocol: docs/taxrag-rq12-protocol.md. Each harness only gathers evidence or repeats his answer call; the
answer itself is always his (rag.generate: SYSTEM_PROMPT, build_prompt over numbered sources, render_citations,
an uncited answer becomes the refusal), so the conditions differ in evidence and retries only.

* V     `answer_with_retry`: his answer call, then up to 2 retries when the reply is empty or stopped at the cap,
        cites nothing by number, or cites numbers that are not sources; a note naming the problem is appended.
* DTR   `deep_tax_research`: plan up to 3 searches, merge their rankings with the question's (RRF), cut to his
        budget, follow the references (R6y), check for gaps, search those, repeat the last two steps.
* DTRa  `research_agent`: the same tools in a ReAct loop (search, follow_references, answer), at most 5 steps.

Everything is reached through `Kit` callables and plain functions, so the harnesses run on his objects in the
evaluation and on fakes in the tests.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable

RRF_K = 60            # his rag.fusion.RRF_K
QUESTION_WEIGHT = 2   # the question's own ranking counts twice in the merge, so sub-queries add rather than replace
MAX_PLAN_QUERIES, MAX_GAP_QUERIES, MAX_QUERY_CHARS = 3, 2, 200
MAX_RETRIES = 2       # the legal H3's MAX_REFLECTION_ROUNDS
MAX_AGENT_STEPS = 5
PREVIOUS_REPLY_CHARS = 1500

PLAN_PROMPT = """You plan searches of the Singapore Income Tax Act 1947 and the IRAS e-Tax guides for a tax question.
List up to 3 short search queries, each for one provision, condition, definition, exception or rule that the answer
needs and that a search for the whole question might miss. Use a section number when the question gives one. Do not
answer the question.

Reply in JSON: {{"queries": ["...", "..."]}}. Reply {{"queries": []}} if a search for the question alone is enough.

Question: {question}"""

GAP_PROMPT = """These numbered sources were found for a Singapore income tax question. Name what a complete answer
still needs that the sources do not contain: up to 2 short search queries, each for one missing provision,
definition, condition or exception (for example a section that a source refers to but that is not among the
sources). Do not answer the question.

Reply in JSON: {{"missing": ["...", "..."]}}. Reply {{"missing": []}} if the sources cover the question.

Sources:

{sources}

Question: {question}"""

AGENT_PROMPT = """You gather evidence from the Singapore Income Tax Act 1947 and the IRAS e-Tax guides so that another
step can answer a tax question from numbered sources. You do not answer the question yourself.

Tools (one per step):
- search {{"query": "..."}}: search for one provision, condition, definition or exception the answer needs. Its results
  are merged into the sources; the sources must fit a fixed budget, so the least relevant ones may drop out.
- follow_references {{"sources": [n, ...]}}: add the provisions that the given sources refer to, define their terms
  in, or continue in (up to {allowance} tokens in all).
- answer {{}}: stop; the sources are complete enough to answer.

Reply in JSON: {{"thought": "...", "tool": "search" | "follow_references" | "answer", "args": {{...}}}}.
Do not repeat a call you have made. You have {left} step(s) left{last}.

Current sources:

{sources}

Steps so far:
{history}

Question: {question}"""

RETRY_NOTES = {
    "cap": "Your previous attempt ran out of its output limit, reasoning included, before it finished the answer. "
           "Keep your reasoning short and write the answer.",
    "uncited": "Your previous reply did not cite the sources by number, so it could not be used. Cite every statement "
               "with source numbers in square brackets, such as [2] or [1][3]. If the sources do not answer the "
               "question, reply with exactly the refusal sentence and nothing else.",
    "invalid": "Your previous reply cited source numbers that do not exist ({numbers}). Cite only [1] to [{n}].",
}
LAST_CAP_NOTE = "This is the last attempt: reason in a few sentences at most, then write the answer."


@dataclass
class Kit:
    """His retrieval pieces, as callables."""
    search: Callable[[str], list]            # query -> his `improved` ranking (his 50 candidates) of chunks
    expand: Callable[..., list]              # (seeds, allowance, present) -> chunks A* adds over dependency edges;
                                             # `present`: other chunks already in the evidence (resolve, cost nothing)
    count_tokens: Callable[[str], int]       # his rag.chunk.count_tokens
    format_source: Callable[[int, object], str]   # his rag.generate.format_source
    budget: int = 2500                       # his CONTEXT_TOKENS
    allowance: int = 450                     # R6y's tuned allowance


@dataclass
class Trace:
    steps: list = field(default_factory=list)       # {"step", ...} per helper call or tool
    queries: list = field(default_factory=list)     # every search query, in order (the question first)

    def log(self, **step) -> None:
        self.steps.append(step)


def parse_json(text: str) -> dict:
    """The reply as a JSON object, or {} (a JSON-mode reply may still carry stray text around it)."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        m = re.search(r"\{.*\}", text or "", re.S)
        try:
            data = json.loads(m.group(0)) if m else {}
        except ValueError:
            data = {}
    return data if isinstance(data, dict) else {}


def clean_queries(raw, question: str, limit: int, earlier: list[str] = ()) -> list[str]:
    """At most `limit` distinct non-empty strings, none of them the question or an earlier query (ignoring case)."""
    out, seen = [], {q.strip().lower() for q in [question, *earlier]}
    for q in raw if isinstance(raw, list) else []:
        if not isinstance(q, str):
            continue
        q = " ".join(q.split())[:MAX_QUERY_CHARS]
        if q and q.lower() not in seen:
            out.append(q)
            seen.add(q.lower())
        if len(out) == limit:
            break
    return out


def merge(rankings: list[list], weights: list[int] | None = None) -> list:
    """Reciprocal-rank fusion of chunk rankings (his RRF, k = 60), ties in order of first appearance."""
    weights = weights or [1] * len(rankings)
    score: dict[str, float] = {}
    first: dict[str, int] = {}
    by_id: dict[str, object] = {}
    for ranking, w in zip(rankings, weights):
        for rank, chunk in enumerate(ranking, start=1):
            cid = chunk.chunk_id
            score[cid] = score.get(cid, 0.0) + w / (RRF_K + rank)
            first.setdefault(cid, len(first))
            by_id[cid] = chunk
    return [by_id[c] for c in sorted(score, key=lambda c: (-score[c], first[c]))]


def within_budget(ranked: list, tokens: int, count_tokens: Callable[[str], int]) -> list:
    """His rag.retrieve.within_budget: the leading chunks that fit (always at least one)."""
    kept, used = [], 0
    for chunk in ranked:
        used += count_tokens(chunk.text)
        if kept and used > tokens:
            break
        kept.append(chunk)
    return kept


def pack(rankings: list[list], kit: Kit) -> list:
    """The question's ranking (first, counted twice) merged with the others, cut to his budget."""
    weights = [QUESTION_WEIGHT] + [1] * (len(rankings) - 1)
    return within_budget(merge(rankings, weights), kit.budget, kit.count_tokens)


def numbered(sources: list, kit: Kit) -> str:
    return "\n\n".join(kit.format_source(n, c) for n, c in enumerate(sources, start=1))


def tokens(chunks: list, kit: Kit) -> int:
    return sum(kit.count_tokens(c.text) for c in chunks)


# ---------------------------------------------------------------------------------------------- validation retry
def problems(raw: str, done_reason: str | None, cited: list, invalid: list, refusal: str) -> list[str]:
    """V1 empty or stopped at the cap, V2 uncited (and not his exact refusal), V3 citation numbers out of range."""
    text = (raw or "").strip()
    if text == refusal:
        return []
    found = []
    if not text or done_reason == "length":
        found.append("cap")
    elif not cited:
        found.append("uncited")
    if invalid:
        found.append("invalid")
    return found


def retry_note(found: list[str], raw: str, invalid: list, n_sources: int, attempt: int = 1,
               retries: int = MAX_RETRIES) -> str:
    """The note appended for retry `attempt` of `retries`. Each retry's note differs from the one before, so a retry
    after a repeated problem is never the same (cached, temperature-0) call again."""
    notes = [RETRY_NOTES[p].format(numbers=", ".join(str(i) for i in dict.fromkeys(invalid)), n=n_sources) for p in found]
    if "cap" in found and attempt == retries and attempt > 1:
        notes.append(LAST_CAP_NOTE)
    text = (raw or "").strip()
    previous = f"\n\nYour previous reply:\n<previous_reply>\n{text[:PREVIOUS_REPLY_CHARS]}\n</previous_reply>" if text and "cap" not in found else ""
    return f"\n\nNote (retry {attempt} of {retries}): " + " ".join(notes) + previous


def answer_with_retry(call: Callable[[str, str], dict], render: Callable[[str], tuple], system: str, user: str,
                      n_sources: int, refusal: str, retries: int = MAX_RETRIES) -> tuple[dict, list[dict]]:
    """His answer call, retried with a note while V1-V3 find a problem. Returns the last reply
    ({"text", "done_reason", ...} from `call`) and every attempt as {"raw", "done_reason", "problems"}."""
    attempts, prompt = [], user
    for attempt in range(retries + 1):
        reply = call(system, prompt)
        raw = reply.get("text", "")
        _, cited, invalid = render(raw)
        found = problems(raw, reply.get("done_reason"), cited, invalid, refusal)
        attempts.append(dict(raw=raw, done_reason=reply.get("done_reason"), problems=found))
        if not found or attempt == retries:
            return reply, attempts
        prompt = user + retry_note(found, raw, invalid, n_sources, attempt + 1, retries)
    raise AssertionError("unreachable")


# ---------------------------------------------------------------------------------------------- Deep Tax Research
def follow_references(hits: list, kit: Kit) -> list:
    """R6y: the hits, then what A* over dependency edges adds within the allowance."""
    return list(hits) + kit.expand(list(hits), kit.allowance, [])


def deep_tax_research(question: str, kit: Kit, helper: Callable[[str], dict], trace: Trace | None = None) -> list:
    """DTR, the fixed pipeline: plan -> search -> follow references -> gap check -> search -> follow references.
    Returns the numbered sources, at R6y's token budget (his 2,500 plus the 450-token allowance)."""
    trace = trace if trace is not None else Trace()
    plan = parse_json(helper(PLAN_PROMPT.format(question=question.strip())).get("text", ""))
    queries = clean_queries(plan.get("queries"), question, MAX_PLAN_QUERIES)
    trace.log(step="plan", queries=queries)
    trace.queries += [question] + queries
    rankings = [kit.search(question)] + [kit.search(q) for q in queries]
    sources = follow_references(pack(rankings, kit), kit)
    gap = parse_json(helper(GAP_PROMPT.format(sources=numbered(sources, kit), question=question.strip())).get("text", ""))
    missing = clean_queries(gap.get("missing"), question, MAX_GAP_QUERIES, queries)
    trace.log(step="gap", missing=missing)
    if missing:
        trace.queries += missing
        rankings += [kit.search(q) for q in missing]
        sources = follow_references(pack(rankings, kit), kit)
    return sources


def research_agent(question: str, kit: Kit, helper: Callable[[str], dict], trace: Trace | None = None,
                   max_steps: int = MAX_AGENT_STEPS) -> list:
    """DTRa: a ReAct loop over search / follow_references / answer, at R6y's token budget. After the agent stops,
    what is left of the allowance goes to R6y from every source, so it never has less than R6y's extra room."""
    trace = trace if trace is not None else Trace()
    trace.queries.append(question)
    rankings = [kit.search(question)]
    hits, extra = pack(rankings, kit), []
    done, history = set(), []

    def current() -> list:
        return hits + [c for c in extra if c not in hits]

    for step in range(1, max_steps + 1):
        sources, left = current(), max_steps - step + 1
        last = "; this is the last step, so reply with the answer tool" if left == 1 else ""
        reply = helper(AGENT_PROMPT.format(allowance=kit.allowance, left=left, last=last, sources=numbered(sources, kit),
                                           history="\n".join(history) or "(none)", question=question.strip()))
        data = parse_json(reply.get("text", ""))
        tool, args = data.get("tool"), data.get("args") if isinstance(data.get("args"), dict) else {}
        if left == 1 or tool == "answer":
            trace.log(step="agent", n=step, tool="answer")
            break
        call = json.dumps([tool, args], sort_keys=True)
        if tool not in ("search", "follow_references"):
            observation = "invalid step: reply with one tool call as JSON"
        elif call in done:
            observation = "already done: choose another call, or answer"
        elif tool == "search":
            query = " ".join(str(args.get("query", "")).split())[:MAX_QUERY_CHARS]
            if not query:
                observation = "invalid step: search needs a query"
            else:
                done.add(call)
                trace.queries.append(query)
                rankings.append(kit.search(query))
                before = {c.chunk_id for c in sources}
                hits = pack(rankings, kit)
                new = [n for n, c in enumerate(current(), start=1) if c.chunk_id not in before]
                observation = f"sources now {len(current())}; new: {new}" if new else "no new sources fit the budget"
        else:
            asked = args.get("sources", [])
            numbers = [n for n in (asked if isinstance(asked, list) else [asked])
                       if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= len(sources)]
            room = kit.allowance - tokens([c for c in extra if c not in hits], kit)
            if not numbers:
                observation = f"invalid step: give source numbers from 1 to {len(sources)}"
            elif room <= 0:
                observation = "the follow-up allowance is used up"
            else:
                done.add(call)
                chosen = [sources[n - 1] for n in dict.fromkeys(numbers)]
                have = {c.chunk_id for c in sources}
                # A* from the chosen sources; the other sources are already present (they resolve, cost nothing)
                kept = [c for c in kit.expand(chosen, room, [c for c in sources if c not in chosen]) if c.chunk_id not in have]
                extra += kept
                observation = f"added {len(kept)} source(s)" if kept else "nothing to add"
        trace.log(step="agent", n=step, tool=tool, args=args, observation=observation)
        history.append(f"{step}. {tool} {json.dumps(args)} -> {observation}")
    sources = current()
    room = kit.allowance - tokens([c for c in extra if c not in hits], kit)
    if room > 0:
        sources = sources + kit.expand(sources, room, [])
    return sources
