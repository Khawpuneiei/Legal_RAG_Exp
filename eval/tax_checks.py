"""Checks behind the qwen3:8b answers in docs/taxrag-results.md.

They cover three things:
- where his 2,000-token cap ran out, and what became of those replies;
- how the model did on the questions with every gold section in the context;
- the abstention gate's effect, projected from the ungated answers for both answer models;
- a fresh re-grade of the test questions where R6y and his `improved` get different correct (all) scores. An incorrect
  answer and an unanswered question both score 0, so those pairs are not re-graded.

    python eval/tax_checks.py regrade-prep   # -> .cache/tax/judge_qwen3-8b/verify_<i>.json: those questions, with the same
                                             # items and labels as the judge batches (IRAS text, not in the repo)
    python eval/tax_checks.py report         # after the panel's grades are in .cache/tax/judge_qwen3-8b/verify_verdicts.json
                                             # -> eval/results/tax/checks_qwen3-8b.md

verify_verdicts.json is a list of {"lens", "verdicts": [{"qid", "label", "verdict"}, ...]}, one entry per judge and file.
Three judges grade each file, each with its own lens:
- in file order;
- first working out the answer from the sources, as an examiner would;
- first comparing the two answers.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.tax_experiment import OUT  # noqa: E402
from eval.tax_judge import SCORE  # noqa: E402
from eval.tax_report import _fmt_diff, paired  # noqa: E402
from src.common import CACHE, read_jsonl  # noqa: E402

SUFFIX = "_qwen3-8b"
JUDGE = CACHE / "tax" / f"judge{SUFFIX}"
MODEL_CACHE = CACHE / "tax-answers-qwen3_8b.jsonl"   # one row per distinct call: v.text, v.completion_tokens
CAP = 2000   # tax_generation.REASONING["qwen3:8b"], his rag.llm.MAX_ANSWER_TOKENS
A, B = "R6y@gemini", "teammate-improved@gemini"
IN_CONTEXT = "structured_routed@gemini+expand"   # his deployed context in graph_per_query.jsonl
NOTE = "One of the two systems declined to answer this question; only the answers listed are graded."


def _differing() -> list[str]:
    by = defaultdict(dict)
    for r in read_jsonl(OUT / f"judge_per_question{SUFFIX}.jsonl"):
        by[r["qid"]][r["condition"]] = r["correct_all"]
    return sorted(q for q, d in by.items() if d[A] != d[B])


def regrade_prep(n_files: int = 2) -> None:
    items = {i["qid"]: i for p in sorted(JUDGE.glob("batch_*.json")) for i in json.loads(p.read_text(encoding="utf-8"))}
    key = json.loads((JUDGE / "key.json").read_text(encoding="utf-8"))["key"]
    out = [dict(items[q], note=NOTE) if key[q].get("REFUSED") else items[q] for q in _differing()]
    per = -(-len(out) // n_files)
    for b in range(n_files):
        (JUDGE / f"verify_{b}.json").write_text(json.dumps(out[b * per:(b + 1) * per], indent=1, ensure_ascii=False),
                                                encoding="utf-8")
    print(len(out), "questions;", sum(len(i["answers"]) for i in out), "answers;", n_files, "files")


def _diff(rows, a, b, metric="correct_all") -> str:
    s, p, wl = _fmt_diff(paired(rows, a, b, metric))
    return f"{s} (Wilcoxon p {p}; higher / lower {wl}, n = {paired(rows, a, b, metric)['n']})"


def cap_lines(lines: list[str]) -> set[str]:
    """The cap: calls that reached it, and what became of each unanswered question. Returns the test questions
    where either configuration got no text back."""
    calls = [r["v"] for r in read_jsonl(MODEL_CACHE)]
    capped = [v for v in calls if v["completion_tokens"] >= CAP]
    cut = {v["text"] for v in capped if v["text"].strip()}
    answers = read_jsonl(CACHE / "tax" / f"generation_answers{SUFFIX}.jsonl")
    gen = {(r["qset"], r["qid"], r["condition"]): r for r in read_jsonl(OUT / f"generation_per_question{SUFFIX}.jsonl")}
    refusal = next(r["text"] for r in answers if gen[(r["qset"], r["qid"], r["condition"])]["refused"])

    def kind(r):
        raw = r["raw"] or ""
        if not raw.strip():
            return "cap, no text"
        if raw in cut:
            return "cap, cut off"
        return "declined" if refusal in raw else "answer without a valid citation"

    by_q = defaultdict(list)
    for r in answers:
        by_q[(r["qset"], r["qid"])].append(r)
    shared = sorted(q for (_, q), rs in by_q.items() if len(rs) == 2 and rs[0]["sources"] == rs[1]["sources"])
    lines += ["## The 2,000-token cap", "",
              f"{len(calls)} distinct model calls for {len(answers)} answers: where both configurations got the same sources "
              f"({', '.join(shared)}), one call answered both. {len(capped)} calls reached the cap, {len(capped) - len(cut)} of "
              f"them with no text (the reasoning used it all) and {len(cut)} cut off partway through the answer. The table "
              f"counts answers, so a shared call counts once per configuration.", "",
              "Unanswered questions by cause: no text at the cap, cut off at the cap, the model's own refusal sentence, "
              "or an answer his checker refused because it cites no source by number. The last column lists the unanswered "
              "questions that were not declined.", "",
              "| Question set | Configuration | Unanswered | Cap, no text | Cap, cut off | Declined | Answer without a valid citation | Unanswered, not declined |",
              "|---|---|---|---|---|---|---|---|"]
    no_text = set()
    for qset, answerable, label in [("heldout", True, "test, answerable"), ("heldout", False, "test, out of scope"),
                                    ("reference", True, "his 28, answerable"), ("reference", False, "his 28, out of scope")]:
        for c in (B, A):
            rows = [r for r in answers if r["qset"] == qset and r["condition"] == c
                    and gen[(qset, r["qid"], c)]["answerable"] == answerable and gen[(qset, r["qid"], c)]["refused"]]
            k = Counter(kind(r) for r in rows)
            lines.append(f"| {label} | `{c}` | {len(rows)} | {k['cap, no text']} | {k['cap, cut off']} | {k['declined']} | "
                         f"{k['answer without a valid citation']} | {', '.join(sorted(r['qid'] for r in rows if kind(r) != 'declined'))} |")
            if qset == "heldout" and answerable:
                no_text |= {r["qid"] for r in rows if kind(r) == "cap, no text"}
    kept = sorted(f"{r['qset']} {r['qid']} `{r['condition']}`" for r in answers
                  if r["raw"] in cut and not gen[(r["qset"], r["qid"], r["condition"])]["refused"])
    lines += ["", f"Cut off at the cap but kept as answers (they cite a source): {', '.join(kept) or 'none'}.", ""]
    return no_text


def report() -> None:
    judged = read_jsonl(OUT / f"judge_per_question{SUFFIX}.jsonl")
    lines = ["# TaxRAG answers (qwen3:8b): checks", "",
             "Paired over the held-out test split's answerable questions: mean A − B [95% bootstrap CI]. "
             f"A = `{A}`, B = `{B}` unless stated. Correct (all): correct 1, partial 0.5, incorrect or unanswered 0.", "",
             f"- As judged (eval/results/tax/judge_summary{SUFFIX}.md): correct (all) {_diff(judged, A, B)}", ""]
    no_text = cap_lines(lines)

    cut_off = {r["qid"] for r in read_jsonl(CACHE / "tax" / f"generation_answers{SUFFIX}.jsonl")
               if r["qset"] == "heldout" and r["raw"] and r["raw"] in
               {v["text"] for v in (x["v"] for x in read_jsonl(MODEL_CACHE)) if v["completion_tokens"] >= CAP}}
    cut_off &= {r["qid"] for r in judged}   # answerable test questions only
    lines += ["## Without the cap failures", "",
              f"- Leaving out the {len(no_text)} test questions where either configuration got no text back "
              f"({', '.join(sorted(no_text))}): correct (all) {_diff([r for r in judged if r['qid'] not in no_text], A, B)}",
              f"- Also leaving out the cut-off replies ({', '.join(sorted(cut_off - no_text)) or 'none'}): correct (all) "
              f"{_diff([r for r in judged if r['qid'] not in no_text | cut_off], A, B)}", ""]

    graph = [r for r in read_jsonl(OUT / "graph_per_query.jsonl") if r["condition"] == IN_CONTEXT and r["split"] == "test"
             and r["answerable"] and r["budget_recall"] == 1.0]
    lines += ["## Every gold section in his deployed context", "",
              f"{len(graph)} test questions; his `improved` answers.", "",
              "| Answer model | Correct | Partial | Incorrect | Unanswered | Correct (all) |", "|---|---|---|---|---|---|"]
    by_model = {}
    for model, suffix in [("qwen2.5:7b", ""), ("qwen3:8b", SUFFIX)]:
        rows = {r["qid"]: r for r in read_jsonl(OUT / f"judge_per_question{suffix}.jsonl") if r["condition"] == B}
        by_model[model] = rows
        k = Counter(rows[r["qid"]]["verdict"] or "unanswered" for r in graph)
        lines.append(f"| {model} | {k['correct']} | {k['partial']} | {k['incorrect']} | {k['unanswered']} | "
                     f"{sum(rows[r['qid']]['correct_all'] for r in graph) / len(graph):.3f} |")
    both = [dict(r, condition=m) for m, rows in by_model.items() for r in rows.values()]
    lines += ["", f"- qwen3:8b vs qwen2.5:7b, his `improved`, all answerable test questions (judged in separate rounds): "
                  f"correct (all) {_diff(both, 'qwen3:8b', 'qwen2.5:7b')}", ""]

    gated = sorted(r["qid"] for r in read_jsonl(OUT / "generation_per_question.jsonl")
                   if r["condition"] == f"{B}+gate" and r["qset"] == "heldout" and r["split"] == "test" and r["answerable"] and r["gated"])
    lines += ["## The abstention gate, projected", "",
              f"The gate depends only on retrieval; on his deployed context it refuses {len(gated)} answerable test questions "
              f"({', '.join(gated)}). Projected from the ungated answers: those questions counted as unanswered (A = gated, "
              f"B = `{B}`).", ""]
    for model, rows in by_model.items():
        base = list(rows.values())
        both = base + [dict(r, condition="gated", correct_all=0.0, wrong_all=0.0) if r["qid"] in gated else dict(r, condition="gated")
                       for r in base]
        lines.append(f"- {model}: their grades {', '.join(rows[q]['verdict'] or 'unanswered' for q in gated)}; correct (all) "
                     f"{_diff(both, 'gated', B)}; wrongly answered {_diff(both, 'gated', B, 'wrong_all')}")
    lines.append("")

    path = JUDGE / "verify_verdicts.json"
    if path.exists():
        key = json.loads((JUDGE / "key.json").read_text(encoding="utf-8"))["key"]
        grades = defaultdict(dict)
        for run in json.loads(path.read_text(encoding="utf-8")):
            for v in run["verdicts"]:
                grades[(v["qid"], v["label"])][run["lens"]] = SCORE[v["verdict"]]
        original = {(r["qid"], lab): r["correct_all"] for r in judged for lab, cs in key[r["qid"]].items()
                    if lab != "REFUSED" and r["condition"] in cs}
        diff = _differing()
        graded = [k for k in original if k[0] in diff]
        median = {k: sorted(grades[k].values())[len(grades[k]) // 2] for k in graded if grades[k]}
        regraded = [dict(r, correct_all=median[(r["qid"], lab)] if lab != "REFUSED" else 0.0)
                    if r["qid"] in diff else r
                    for r in judged for lab in [next(lab for lab, cs in key[r["qid"]].items() if r["condition"] in cs)]]
        lines += ["## Fresh re-grade of the questions where the two differ in correct (all)", "",
                  f"{len(diff)} questions, {len(graded)} graded answers, {sum(len(grades[k]) == 3 for k in graded)} graded by "
                  f"all three lenses.", "",
                  f"- The three lenses agree on {sum(len(set(grades[k].values())) == 1 for k in graded)} of {len(graded)}; "
                  f"their median equals the original grade on {sum(median[k] == original[k] for k in median)}.",
                  f"- With the panel's median grade on these questions: correct (all) {_diff(regraded, A, B)}", ""]
    (OUT / f"checks{SUFFIX}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    if sys.argv[1:2] == ["regrade-prep"]:
        regrade_prep()
    elif sys.argv[1:2] == ["report"]:
        report()
    else:
        raise SystemExit(__doc__)
