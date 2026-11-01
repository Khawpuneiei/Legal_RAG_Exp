"""Deep Tax Research, the validation retry and the tax skill loader (src/tax/research.py, src/tax/skill.py).

No network and no model: chunks are plain objects, his search and A* expansion are scripted callables, and the helper
and answer calls replay fixed replies.
"""
import json
from dataclasses import dataclass

import pytest

from src.tax import research as rs
from src.tax import skill as sk

REFUSAL = "I can't answer this from the sources."


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    text: str


def chunk(cid: str, words: int = 10) -> Chunk:
    return Chunk(cid, " ".join(["w"] * words))


def count_tokens(text: str) -> int:
    return len(text.split())


def kit(rankings: dict, deps: dict | None = None, budget: int = 30, allowance: int = 15, log: list | None = None) -> rs.Kit:
    """Search returns the scripted ranking for a query; expand adds each pinned chunk's scripted dependencies that fit."""
    deps = deps or {}

    def search(query):
        if log is not None:
            log.append(("search", query))
        return list(rankings.get(query, []))

    def expand(pinned, room, present=()):
        if log is not None:
            log.append(("expand", [c.chunk_id for c in pinned], room))
        have, out, used = {c.chunk_id for c in [*pinned, *present]}, [], 0
        for c in pinned:
            for d in deps.get(c.chunk_id, []):
                if d.chunk_id not in have and used + count_tokens(d.text) <= room:
                    out.append(d)
                    have.add(d.chunk_id)
                    used += count_tokens(d.text)
        return out

    return rs.Kit(search, expand, count_tokens, lambda n, c: f"[{n}] {c.chunk_id}\n{c.text}", budget, allowance)


def replies(*texts):
    """A helper or answer callable that returns the scripted texts in order and records each prompt."""
    seen = []

    def call(*args):
        seen.append(args)
        text = texts[len(seen) - 1]
        return text if isinstance(text, dict) else {"text": text, "done_reason": "stop"}

    call.seen = seen
    return call


# ------------------------------------------------------------------------------------------------ merging evidence
def test_the_questions_ranking_alone_packs_to_his_hits_within_the_budget():
    a, b, c, d = chunk("a"), chunk("b"), chunk("c"), chunk("d")
    k = kit({"q": [a, b, c, d]}, budget=25)
    assert [x.chunk_id for x in rs.pack([k.search("q")], k)] == ["a", "b"]   # his within_budget: stop at the first that does not fit


def test_the_question_counts_twice_so_a_sub_query_adds_rather_than_replaces():
    a, b, c, x = chunk("a"), chunk("b"), chunk("c"), chunk("x")
    merged = rs.merge([[a, b, c], [x, c]], [rs.QUESTION_WEIGHT, 1])
    assert [m.chunk_id for m in merged] == ["c", "a", "b", "x"]   # c is in both lists; x, top of the sub-query only, comes last


def test_ties_keep_the_order_of_first_appearance():
    a, b = chunk("a"), chunk("b")
    assert [m.chunk_id for m in rs.merge([[a], [b]])] == ["a", "b"]


def test_queries_are_cleaned_capped_and_never_the_question_itself():
    raw = ["  section 37B  ", "Section 37B", "", 7, "What is group relief?", "loss transfer", "a third", "a fourth"]
    assert rs.clean_queries(raw, "What is group relief?", 3) == ["section 37B", "loss transfer", "a third"]
    assert rs.clean_queries("not a list", "q", 3) == []


def test_json_replies_are_parsed_even_with_stray_text():
    assert rs.parse_json('{"queries": ["a"]}') == {"queries": ["a"]}
    assert rs.parse_json('Sure: {"missing": []} done') == {"missing": []}
    assert rs.parse_json("no json") == {} and rs.parse_json("[1, 2]") == {}


# ------------------------------------------------------------------------------------------------ validation retry
@pytest.mark.parametrize("raw, done, cited, invalid, expected", [
    (REFUSAL, "stop", [], [], []),
    ("", "length", [], [], ["cap"]),
    ("Half an answer [1]", "length", ["c"], [], ["cap"]),
    ("Section 37B allows it.", "stop", [], [], ["uncited"]),
    ("It is allowed [1][9].", "stop", ["c"], [9], ["invalid"]),
    ("It is allowed [1].", "stop", ["c"], [], []),
], ids=["own-refusal", "empty-at-cap", "cut-off", "uncited", "invalid-number", "fine"])
def test_the_validator_flags_the_three_problems_and_never_the_models_own_refusal(raw, done, cited, invalid, expected):
    assert rs.problems(raw, done, cited, invalid, REFUSAL) == expected


def render_for(n_sources: int):
    def render(raw):
        nums = [int(x) for x in __import__("re").findall(r"\[(\d+)\]", raw)]
        return raw, [n for n in nums if 1 <= n <= n_sources], [n for n in nums if not 1 <= n <= n_sources]
    return render


def test_a_failed_reply_is_retried_with_a_note_and_the_previous_reply_when_there_is_one():
    call = replies({"text": "", "done_reason": "length"}, "Section 37B allows it.", "Section 37B allows it [1].")
    reply, attempts = rs.answer_with_retry(call, render_for(2), "SYS", "USER", 2, REFUSAL)
    assert reply["text"] == "Section 37B allows it [1]."
    assert [a["problems"] for a in attempts] == [["cap"], ["uncited"], []]
    first_retry, second_retry = call.seen[1][1], call.seen[2][1]
    assert first_retry.startswith("USER\n\nNote (retry 1 of 2): Your previous attempt ran out") and "<previous_reply>" not in first_retry
    assert second_retry.startswith("USER\n\nNote (retry 2 of 2): Your previous reply did not cite")
    assert "did not cite" in second_retry and "<previous_reply>\nSection 37B allows it.\n</previous_reply>" in second_retry


def test_a_second_cap_failure_gets_a_different_prompt_not_the_same_cached_call():
    call = replies({"text": "", "done_reason": "length"}, {"text": "", "done_reason": "length"}, "Yes [1].")
    reply, attempts = rs.answer_with_retry(call, render_for(1), "SYS", "USER", 1, REFUSAL)
    prompts = [seen[1] for seen in call.seen]
    assert len(set(prompts)) == 3 and rs.LAST_CAP_NOTE in prompts[2] and rs.LAST_CAP_NOTE not in prompts[1]
    assert reply["text"] == "Yes [1]."


def test_retries_stop_after_two_and_the_last_reply_stands():
    call = replies("no cites", "still none", "none again", "never asked")
    reply, attempts = rs.answer_with_retry(call, render_for(1), "SYS", "USER", 1, REFUSAL)
    assert len(call.seen) == 3 and reply["text"] == "none again" and attempts[-1]["problems"] == ["uncited"]


def test_the_models_own_refusal_is_not_retried():
    call = replies(REFUSAL, "never asked")
    reply, attempts = rs.answer_with_retry(call, render_for(1), "SYS", "USER", 1, REFUSAL)
    assert len(call.seen) == 1 and reply["text"] == REFUSAL


def test_an_invalid_number_names_the_valid_range():
    call = replies("Yes [1][7].", "Yes [1].")
    rs.answer_with_retry(call, render_for(3), "SYS", "USER", 3, REFUSAL)
    assert "do not exist (7). Cite only [1] to [3]." in call.seen[1][1]


# ------------------------------------------------------------------------------------------------ Deep Tax Research
def test_with_nothing_planned_or_missing_research_equals_r6y():
    a, b, d = chunk("a"), chunk("b"), chunk("d", 5)
    k = kit({"q": [a, b]}, deps={"a": [d]})
    helper = replies('{"queries": []}', '{"missing": []}')
    assert rs.deep_tax_research("q", k, helper) == rs.follow_references(rs.pack([k.search("q")], k), k) == [a, b, d]


def test_research_searches_the_plan_and_the_gaps_then_follows_the_references():
    a, b, x, y, dx = chunk("a"), chunk("b"), chunk("x"), chunk("y"), chunk("dx", 5)
    log = []
    k = kit({"q": [a, b], "s 37B": [x], "loss": [y]}, deps={"x": [dx]}, budget=30, log=log)
    helper = replies('{"queries": ["s 37B", "q", "s 37B"]}', '{"missing": ["loss", "s 37B"]}')
    trace = rs.Trace()
    sources = rs.deep_tax_research("q", k, helper, trace)
    assert [s for s in log if s[0] == "search"] == [("search", "q"), ("search", "s 37B"), ("search", "loss")]
    assert trace.queries == ["q", "s 37B", "loss"]
    assert [c.chunk_id for c in sources] == ["a", "b", "x", "dx"]   # merged hits within 30 tokens (y does not fit), then x's dependency
    assert "[1] a" in helper.seen[1][0] and "Question: q" in helper.seen[1][0]   # the gap check sees the numbered sources


def test_the_agent_searches_refuses_a_repeat_follows_references_and_fills_the_rest():
    a, b, x, da, dx = chunk("a"), chunk("b"), chunk("x"), chunk("da", 5), chunk("dx", 5)
    log = []
    k = kit({"q": [a, b], "s 37B": [x]}, deps={"a": [da], "x": [dx]}, budget=30, allowance=10, log=log)
    helper = replies(json.dumps({"tool": "search", "args": {"query": "s 37B"}}),
                     json.dumps({"tool": "search", "args": {"query": "s 37B"}}),
                     json.dumps({"tool": "follow_references", "args": {"sources": [1]}}),
                     json.dumps({"tool": "answer", "args": {}}))
    trace = rs.Trace()
    sources = rs.research_agent("q", k, helper, trace)
    assert [s["tool"] for s in trace.steps] == ["search", "search", "follow_references", "answer"]
    assert trace.steps[1]["observation"].startswith("already done")
    assert [c.chunk_id for c in sources] == ["a", "b", "x", "da", "dx"]   # da from the agent's call, dx from the final fill
    assert log[-1] == ("expand", ["a", "b", "x", "da"], 5)                # the 5 tokens left of the allowance


def test_following_references_counts_the_other_sources_as_present_so_they_cost_no_allowance():
    a, b, c = chunk("a"), chunk("b"), chunk("c")
    k = kit({"q": [a, b, c]}, budget=30, allowance=10)
    seen = []
    k.expand = lambda seeds, room, present=(): seen.append(([s.chunk_id for s in seeds], room, [p.chunk_id for p in present])) or []
    helper = replies(json.dumps({"tool": "follow_references", "args": {"sources": [2, 2]}}), json.dumps({"tool": "answer"}))
    rs.research_agent("q", k, helper, rs.Trace())
    assert seen[0] == (["b"], 10, ["a", "c"])          # A* from source 2 only; 1 and 3 already resolve what they can
    assert seen[1] == (["a", "b", "c"], 10, [])       # the final R6y fill from every source


def test_the_real_graph_does_not_spend_the_allowance_on_a_present_dependency():
    """ClauseGraph.astar with `present`: a dependency already in the evidence is not re-added or paid for."""
    import numpy as np
    from src.retrieval.graph import ClauseGraph
    g = ClauseGraph.__new__(ClauseGraph)
    g.clauses = {i: {"text": " ".join(["w"] * n)} for i, n in [("s", 5), ("p", 20), ("d", 5)]}
    g.emb = {i: np.zeros(2) for i in g.clauses}
    g.token_fn = count_tokens
    g.seed_only_types = set()
    g.out = {"s": [("p", "REFERS_TO", 0.3), ("d", "DEFINED_IN", 0.2)], "p": [], "d": []}
    g.deps = {"s": [{"p"}, {"d"}], "p": [], "d": []}
    g.unresolved = lambda cid, ev: sum(1 for group in g.deps.get(cid, []) if not group & ev)
    without = g.astar(["s"], np.zeros(2), 5 + 10, lam=0, mu=0, pinned=True)["evidence"]
    with_p = g.astar(["s"], np.zeros(2), 5 + 20 + 10, lam=0, mu=0, pinned=True, present=["p"])["evidence"]
    assert without == ["s", "d"]                      # p (20 tokens) does not fit the 10-token allowance
    assert with_p == ["s", "p", "d"]                  # p is present: d is added, nothing paid for p


def test_the_agent_must_answer_on_its_last_step():
    a = chunk("a")
    k = kit({"q": [a]})
    helper = replies(*[json.dumps({"tool": "search", "args": {"query": f"q{i}"}}) for i in range(3)])
    trace = rs.Trace()
    rs.research_agent("q", k, helper, trace, max_steps=3)
    assert len(helper.seen) == 3 and "this is the last step" in helper.seen[2][0] and trace.steps[-1]["tool"] == "answer"


def test_a_bad_step_is_reported_back_and_costs_a_step():
    a = chunk("a")
    k = kit({"q": [a]})
    helper = replies("not json", json.dumps({"tool": "follow_references", "args": {"sources": [9, True]}}),
                     json.dumps({"tool": "answer"}))
    trace = rs.Trace()
    rs.research_agent("q", k, helper, trace)
    assert trace.steps[0]["observation"].startswith("invalid step")
    assert trace.steps[1]["observation"] == "invalid step: give source numbers from 1 to 1"


# ------------------------------------------------------------------------------------------------ the skill
@pytest.fixture
def skill(tmp_path, monkeypatch):
    base = tmp_path / "tax-answering"
    (base / "modules").mkdir(parents=True)
    (base / "SKILL.md").write_text("---\nname: tax-answering\ndescription: Answer tax questions.\n---\n\n# Steps\n\nRead.\n\n"
                                   "## Modules\n\n- `modules/group-relief.md`: group relief\n- `modules/carry-back.md`: carry-back\n"
                                   "- `modules/missing.md`: not written\n", encoding="utf-8")
    (base / "modules" / "group-relief.md").write_text("Check the group.", encoding="utf-8")
    (base / "modules" / "carry-back.md").write_text("Check the loss.", encoding="utf-8")
    monkeypatch.setattr(sk, "SKILLS", tmp_path)
    return sk.read_skill()


def test_the_module_index_comes_from_skill_md_and_lists_only_files_that_exist(skill):
    assert skill["name"] == "tax-answering" and skill["description"] == "Answer tax questions."
    assert list(skill["index"]) == ["modules/group-relief.md", "modules/carry-back.md"]
    assert skill["modules"]["modules/carry-back.md"] == "Check the loss."


def test_routing_keeps_the_models_order_matches_file_names_and_ignores_empty_names(skill):
    assert sk.chosen_modules(skill, {"load": ["", "carry-back.md", "modules/group-relief.md"]}) == \
        ["modules/carry-back.md", "modules/group-relief.md"]
    assert sk.chosen_modules(skill, {"load": [""]}) == []
    assert sk.chosen_modules(skill, {"load": "modules/carry-back.md"}) == []
    assert sk.chosen_modules(skill, {}) == []


def test_the_comprehensive_text_and_the_block_have_the_legal_shapes(skill):
    text = sk.comprehensive_text(skill)
    assert text.startswith("# Steps") and "---\n## Module: modules/group-relief.md\n\nCheck the group." in text
    block = sk.skill_block("tax-answering", "BODY", {"modules/carry-back.md": "Check the loss."})
    assert block == ('<skill name="tax-answering">\nBODY\n</skill>\n\n'
                     '<skill_file path="modules/carry-back.md">\nCheck the loss.\n</skill_file>')
    assert "at most 2 files" in sk.route_prompt(skill, "Q?") and "- modules/carry-back.md: carry-back" in sk.route_prompt(skill, "Q?")
