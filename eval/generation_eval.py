"""Generation and grounding evaluation for Experiment 3 (docs/project-plan.md section 5.4, grounding metrics).

For every request in the synthetic test split (90; --n draws a seeded subset), a local LLM (Ollama) is
asked to pick an approved clause for each requirement in the request and to quote the clause text that
supports the pick. Conditions differ only in what the model is shown:

  R0  nothing (no retrieval): the model must draft from its own knowledge
  R1  clauses covered by the top-5 naive fixed-size chunks
  R4  top-5 clauses from hybrid + reranker
  R5  top-5 clauses from R4 + contextual enrichment

Metrics (computed deterministically, no LLM judge):
  citation_accuracy     cited clause_id exists and is a gold clause for one of the request's asks
  hallucinated_rate     selections not traceable to the library (fabricated id, or drafted text with no id)
  claim_support         cited selections whose evidence quote (>= 8 words) appears verbatim in the cited clause
  ask_recall            share of the request's asks satisfied by a correct citation
  abstention_lenient    (item level, kept for comparison) for requests containing an unsupported ask: the model
                        left at least one requirement unmatched (clause_id null), whichever requirement it was

Per-requirement abstention (requests containing an unsupported ask). Selections are aligned one-to-one to the
request's asks and unsupported asks by the words of their "requirement" field (see align()); what the model cited
plays no part in the alignment. Each unsupported ask then has exactly one outcome:
  correct_abstention    the selection aligned to it has clause_id null and no drafted text
  false_citation        the selection aligned to it cites some clause_id
  missing_ask_drafted   the selection aligned to it has clause_id null but carries a drafted clause (>= 8 words)
  missing_ask_omitted   no selection aligned to it: the model dropped the requirement silently
  align_agreement       diagnostic: of the selections that correctly cite the gold clause of exactly one ask, the
                        share the alignment assigns to that ask (the rest are unaligned or, rarely, on another ask)

A clause_id counts as a library id if it matches one after dropping a copied "clause_id:" label, brackets and case.

Usage:  python eval/generation_eval.py [--n 90] [--seeds 1 2 3]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import clause_catalog as cat  # noqa: E402
from eval.metrics.retrieval_metrics import bootstrap_ci  # noqa: E402
from src.common import ROOT, load_synthetic, read_jsonl  # noqa: E402
from src.llm.ollama import OllamaLLM  # noqa: E402

OUT = ROOT / "eval" / "results" / "exp3"
CONDITIONS = ["R0", "R1", "R4", "R5"]

SYSTEM = ("You are a legal drafting assistant at a Singapore fund management company regulated by the Monetary "
          "Authority of Singapore. Accuracy matters more than completeness.")
PROMPT_RAG = """Request from a colleague:
<request>
{request}
</request>

Approved clause library excerpts (the ONLY clauses you may use):
{clauses}

For each specific requirement or special term in the request (ignore routine drafting of the standard template), select the approved clause above that satisfies it.
Return JSON: {{"selections": [{{"requirement": "<short description>", "clause_id": "<clause_id from the excerpts, or null>", "evidence_quote": "<an exact quote of at least 8 consecutive words from the selected clause, or empty>"}}]}}
If none of the excerpts satisfies a requirement, set clause_id to null and evidence_quote to "". Never invent a clause_id."""
PROMPT_R0 = """Request from a colleague:
<request>
{request}
</request>

You do not have access to the firm's approved clause library. For each specific requirement or special term in the request (ignore routine drafting of the standard template), draft a suitable clause.
Return JSON: {{"selections": [{{"requirement": "<short description>", "clause_id": null, "evidence_quote": "<your drafted clause text>"}}]}}"""


def norm(s: str) -> str:
    s = s.lower().replace("’", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[^a-z0-9%.' ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip(" .")


def quote_supported(quote: str, clause_text: str) -> bool:
    q = norm(quote)
    return len(q.split()) >= 8 and q in norm(clause_text)


def ask_gold(agreement_type: str, ask: str, by_key_to_id: dict[str, str]) -> set[str]:
    g = cat.ASKS[ask]["gold"]
    return {by_key_to_id[k] for k, grade in (g.get(agreement_type) or g["*"]).items() if grade >= 2}


ID_LABEL = re.compile(r"^clause[_ ]?id\s*:\s*", re.I)
NULL_IDS = {"", "null", "none", "n/a"}


def resolve_id(raw, id_lookup: dict[str, str]) -> str | None:
    """None for an empty/null clause_id; the library id it names (ignoring a copied "clause_id:" label, brackets and
    case); otherwise the raw string, which is then scored as fabricated."""
    if raw is None:
        return None
    s = str(raw).strip().strip("[]\"' ").strip()
    s = ID_LABEL.sub("", s).strip()
    if s.lower() in NULL_IDS:
        return None
    return id_lookup.get(s.upper(), s)


# --- alignment of selections to asks -------------------------------------------------------------------------
ALIGN_MIN = 0.3  # minimum IDF-weighted cosine between a requirement and an ask phrasing
STOP = set("""a about after all also an and any are as at be been being but by can could do does each even every for from
get gets give go has have he her his how i if in into is it its just let like make makes many may me more much must my
need needs no not of on one only or other our out over please put same see she should so some such than that the their
them then there these they this those to too under up us very want wants was we well were what when where which while
who will with would you your clause clauses include including add ensure provide provision requirement""".split())


def _stem(w: str) -> str:
    """Crude stemmer: drop -ing/-ed, undouble the last consonant, keep a 5-letter prefix
    (topping/top, tokens/token, custody/custodian, compliance/compliant)."""
    for suf in ("ing", "ed"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)]
            if len(w) >= 3 and w[-1] == w[-2] and w[-1] not in "aeiouls":
                w = w[:-1]
            break
    return w[:5]


def _terms(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", str(text).lower().replace("’", "'"))
    return {_stem(w) for w in words if w not in STOP and (len(w) > 1 or w.isdigit())}


def _ask_texts() -> dict[str, list[str]]:
    texts = {a: spec["phrasings"] + [a.replace("_", " ")] for a, spec in cat.ASKS.items()}
    texts.update({m: phr + [m.replace("_", " ")] for m, phr in cat.MISSING_ASKS.items()})
    return texts


ASK_TEXTS = _ask_texts()
_DOCS = [_terms(t) for ts in ASK_TEXTS.values() for t in ts]
IDF = {t: float(np.log((len(_DOCS) + 1) / (sum(t in d for d in _DOCS) + 1)) + 1) for d in _DOCS for t in d}
IDF_MAX = float(np.log(len(_DOCS) + 1) + 1)


def _cosine(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    w = lambda t: IDF.get(t, IDF_MAX) ** 2  # noqa: E731
    return sum(w(t) for t in a & b) / float(np.sqrt(sum(w(t) for t in a) * sum(w(t) for t in b)))


def ask_similarity(requirement: str, ask: str) -> float:
    """Best IDF-weighted cosine between a requirement and any catalogue phrasing of the ask (or its name)."""
    r = _terms(requirement)
    return max(_cosine(r, _terms(t)) for t in ASK_TEXTS[ask])


def align(requirements: list[str], targets: list[str]) -> list[tuple[str | None, float]]:
    """One-to-one alignment of requirements to target asks maximising total similarity; pairs below ALIGN_MIN are
    dropped. Returns, per requirement, (aligned ask or None, similarity of that pair or of its best ask)."""
    if not requirements or not targets:
        return [(None, 0.0)] * len(requirements)
    sim = np.array([[ask_similarity(r, t) for t in targets] for r in requirements])
    out = [(None, round(float(row.max()), 3)) for row in sim]
    for i, j in zip(*linear_sum_assignment(sim, maximize=True)):
        if sim[i, j] >= ALIGN_MIN:
            out[i] = (targets[j], round(float(sim[i, j]), 3))
    return out


def choose_items(ds, n: int, seed: int = 7) -> list:
    test = [q for q in ds.queries if q.meta["split"] == "test"]
    if n <= 0 or n >= len(test):
        return sorted(test, key=lambda q: q.qid)
    rng = random.Random(seed)
    missing = [q for q in test if q.meta["missing_asks"]]
    rest = [q for q in test if not q.meta["missing_asks"]]
    k_missing = min(len(missing), max(5, n // 6))
    items = rng.sample(missing, k_missing) + rng.sample(rest, n - k_missing)
    return sorted(items, key=lambda q: q.qid)


def parse(text: str) -> list[dict]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    sel = data.get("selections", []) if isinstance(data, dict) else []
    return [s for s in sel if isinstance(s, dict)]


def score(q, selections: list[dict], clauses: dict, by_key_to_id: dict, shown: set[str]) -> dict:
    id_lookup = {cid.upper(): cid for cid in clauses}
    sels = [dict(cid=resolve_id(s.get("clause_id"), id_lookup), quote=str(s.get("evidence_quote") or ""),
                 requirement=str(s.get("requirement") or "")) for s in selections]
    drafted = lambda s: len(s["quote"].split()) >= 8  # noqa: E731
    gold_any = {cid for cid, g in q.graded.items() if g >= 2}
    cited = [s for s in sels if s["cid"] is not None]
    valid = [s for s in cited if s["cid"] in clauses]
    correct = [s for s in valid if s["cid"] in gold_any]
    supported = [s for s in valid if quote_supported(s["quote"], clauses[s["cid"]]["text"])]
    fabricated = [s for s in cited if s["cid"] not in clauses]
    uncited_drafts = [s for s in sels if s["cid"] is None and drafted(s)]
    asks, missing = q.meta["asks"], q.meta["missing_asks"]
    gold_of = {a: ask_gold(q.meta["agreement_type"], a, by_key_to_id) for a in asks}
    cited_ids = {s["cid"] for s in valid}
    satisfied = [a for a in asks if cited_ids & gold_of[a]]
    m = dict(n_selections=len(sels), n_cited=len(cited),
             n_id_normalised=sum(1 for s, raw in zip(sels, selections) if s["cid"] in clauses and raw.get("clause_id") != s["cid"]),
             citation_accuracy=(len(correct) / len(cited)) if cited else float("nan"),
             hallucinated_rate=((len(fabricated) + len(uncited_drafts)) / len(sels)) if sels else float("nan"),
             claim_support=(len(supported) / len(valid)) if valid else float("nan"),
             ask_recall=(len(satisfied) / len(asks)) if asks else float("nan"),
             outside_context=(sum(1 for s in valid if s["cid"] not in shown) / len(valid)) if valid and shown else float("nan"))
    aligned = align([s["requirement"] for s in sels], asks + missing)
    m["aligned_to"] = [a for a, _ in aligned]
    # diagnostic: does the text alignment agree with the clause the model correctly cited?
    checks = [(s, a) for s, (a, _) in zip(sels, aligned) if s["cid"] in clauses and sum(s["cid"] in g for g in gold_of.values()) == 1]
    m["n_align_check"] = len(checks)
    m["n_align_agree"] = sum(1 for s, a in checks if a in gold_of and s["cid"] in gold_of[a])
    m["n_align_other"] = sum(1 for s, a in checks if a is not None and not (a in gold_of and s["cid"] in gold_of[a]))
    if missing:
        m["abstention_lenient"] = 1.0 if any(s["cid"] is None for s in sels) else 0.0
        outcomes = {}
        for ask in missing:
            match = next((s for s, (a, _) in zip(sels, aligned) if a == ask), None)
            if match is None:
                outcomes[ask] = "omitted"
            elif match["cid"] is not None:
                outcomes[ask] = "false_citation"
            elif drafted(match):
                outcomes[ask] = "drafted"
            else:
                outcomes[ask] = "abstained"
        m["missing_ask_outcomes"] = outcomes
        for key, outcome in [("correct_abstention", "abstained"), ("false_citation", "false_citation"),
                             ("missing_ask_drafted", "drafted"), ("missing_ask_omitted", "omitted")]:
            m[key] = sum(o == outcome for o in outcomes.values()) / len(outcomes)
    return m


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=90, help="requests (default: the whole 90-request test split)")
    ap.add_argument("--seeds", type=int, nargs="*", default=[1, 2, 3])
    ap.add_argument("--temperature", type=float, default=0.3)
    args = ap.parse_args()
    ds = load_synthetic()
    clauses = ds.meta["clauses"]
    by_key_to_id = {c["key"]: cid for cid, c in clauses.items()}
    rankings = {(r["condition"], r["qid"]): r for r in read_jsonl(OUT / "rankings.jsonl") if r["dataset"] == "synthetic"}
    items = choose_items(ds, args.n)
    llm = OllamaLLM(num_ctx=8192, cache_name="gen")
    rows = []
    for cond in CONDITIONS:
        for q in items:
            if cond == "R0":
                shown, prompt = set(), PROMPT_R0.format(request=q.text)
            else:
                units = rankings[(cond, q.qid)]["unit_ids"]
                if cond == "R1":
                    # all clauses covered by the top-5 fixed chunks (naive RAG passes whole windows)
                    from src.retrieval.chunking import fixed_chunks
                    from eval.metrics.retrieval_metrics import chunk_units
                    if not hasattr(main, "_r1"):
                        ch = fixed_chunks(ds)
                        main._r1 = (ch, chunk_units(ds, ch))
                    ch, cov = main._r1
                    idx = {c.chunk_id: i for i, c in enumerate(ch)}
                    shown_list = []
                    for cid in rankings[(cond, q.qid)]["chunk_ids"][:5]:
                        for u in cov[idx[cid]]:
                            if u not in shown_list:
                                shown_list.append(u)
                else:
                    shown_list = units[:5]
                shown = set(shown_list)
                block = "\n\n".join(f"[clause_id: {u}] {clauses[u]['title']}\n{clauses[u]['text']}" for u in shown_list)
                prompt = PROMPT_RAG.format(request=q.text, clauses=block)
            for seed in args.seeds:
                out = llm.generate(prompt, system=SYSTEM, temperature=args.temperature, seed=seed, json_mode=True, max_tokens=700)
                sel = parse(out["text"])
                m = score(q, sel, clauses, by_key_to_id, shown)
                rows.append(dict(condition=cond, qid=q.qid, seed=seed, latency_s=out["latency_s"], context_clauses=len(shown), **m,
                                 raw=out["text"][:4000]))
            print(f"  {cond} {q.qid} done")
    llm.unload()
    with open(OUT / "generation_per_item.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    lines, summary = summarise(rows, items, args.seeds, args.temperature, llm.model)
    (OUT / "generation_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT / "generation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("\n".join(lines))


def _table(rows: list[dict], items: list, metrics: list[str], summary: list[dict]) -> list[str]:
    lines = ["| Condition | " + " | ".join(metrics) + " |", "|---|" + "---|" * len(metrics)]
    for cond in CONDITIONS:
        cells = []
        for m in metrics:
            per_item = []
            for q in items:
                vals = [r[m] for r in rows if r["condition"] == cond and r["qid"] == q.qid and m in r and not (isinstance(r[m], float) and np.isnan(r[m]))]
                if vals:
                    per_item.append(float(np.mean(vals)))
            mean, lo, hi = bootstrap_ci(per_item) if per_item else (float("nan"),) * 3
            summary.append(dict(condition=cond, metric=m, mean=mean, ci_low=lo, ci_high=hi, n=len(per_item)))
            if np.isnan(mean):
                cells.append("–")
            elif m in ("n_selections", "context_clauses", "latency_s"):
                cells.append(f"{mean:.1f}")
            else:
                cells.append(f"{mean:.3f} [{lo:.3f}, {hi:.3f}]")
        lines.append(f"| {cond} | " + " | ".join(cells) + " |")
    return lines


def summarise(rows: list[dict], items: list, seeds: list[int], temperature: float, model: str) -> tuple[list[str], list[dict]]:
    n_missing = sum(1 for q in items if q.meta["missing_asks"])
    test_n = sum(1 for q in load_synthetic().queries if q.meta["split"] == "test")
    sample = f"All {len(items)} requests of the held-out test split" if len(items) == test_n else f"{len(items)} requests from the held-out test split (seeded sample)"
    summary: list[dict] = []
    lines = ["# Experiment 3: generation and grounding (synthetic test split)", "",
             f"{sample}, {n_missing} of which contain an ask the library cannot satisfy; "
             f"{len(seeds)} seeds each, temperature {temperature}, model {model} via Ollama. Per-request means are averaged over seeds, "
             "then over requests; brackets are 95% bootstrap CIs over requests.", "",
             "## All requests", ""]
    lines += _table(rows, items, ["citation_accuracy", "hallucinated_rate", "claim_support", "ask_recall", "n_selections", "context_clauses", "latency_s"], summary)
    lines += ["", f"## Unsupported asks ({n_missing} requests, one unsupported ask each)", "",
              "Per-requirement outcome of the unsupported ask (the four outcomes sum to 1), then the old item-level metric, "
              "which counts any null selection anywhere in the request.", ""]
    lines += _table(rows, items, ["correct_abstention", "false_citation", "missing_ask_drafted", "missing_ask_omitted", "abstention_lenient"], summary)
    agree = []
    for cond in CONDITIONS:
        chk, ok, other = (sum(r.get(k, 0) for r in rows if r["condition"] == cond) for k in ("n_align_check", "n_align_agree", "n_align_other"))
        if chk:
            agree.append(f"{cond} {ok}/{chk} ({ok / chk:.1%}; {other} on another ask)")
        summary.append(dict(condition=cond, metric="align_agreement", mean=(ok / chk) if chk else float("nan"), n=chk, n_other_ask=other))
    lines += ["", "Alignment check: of the selections that correctly cite the gold clause of exactly one ask, the share the "
              "text alignment assigns to that same ask (the rest stay unaligned unless noted): " + "; ".join(agree) + ".", "",
              "Metric definitions are in the docstring of `eval/generation_eval.py`. R0 has no library, so its citation metrics "
              "are undefined, every drafted clause counts as not traceable to the library, and it is told to draft rather than abstain."]
    return lines, summary


if __name__ == "__main__":
    main()
