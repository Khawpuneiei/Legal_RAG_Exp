"""Claude in the teammate's tax RAG against existing tax chatbots, on the held-out test questions, judged blind.

Systems, each a row in the judging:
- `claude-rag`: Claude Opus 5.5 in his deployed pipeline (`tax_generation.py --model claude`, `teammate-improved@gemini`);
- `qwen3-rag`: qwen3:8b, the earlier stand-in for his gpt-oss-120b, in the same pipeline (RQ1/RQ2 condition B0);
- `claude-closed`: Claude Opus 5.5 without retrieval, given only the question (what the model knows by itself);
- one row per external chatbot, its answers copied from its public web page into .cache/tax/chatbots/<name>.jsonl
  ({"qid", "text", "asked_at", "url"} per line), on the seeded sample of answerable questions.

    python eval/tax_chatbots.py sample                        # -> eval/results/tax/chatbot_sample.json (seeded, fixed)
    python eval/tax_chatbots.py closed-book [--all]           # Claude without retrieval: the sample, or every answerable test question
    python eval/tax_chatbots.py prep 6 claude-rag qwen3-rag claude-closed [bot ...] [--all]   # -> .cache/tax/judge_chatbots/
    python eval/tax_chatbots.py score [--exclude chat-gov-sg]   # verdicts.json -> chatbot_judge_per_question.jsonl, chatbot_summary.md
    python eval/tax_chatbots.py regrade-prep                  # the sample's answers -> regrade_0.json, regrade_1.json
    python eval/tax_chatbots.py regrade-score [--exclude chat-gov-sg]   # regrade_verdicts.json -> chatbot_regrade_summary.md
    python eval/tax_chatbots.py prep 4 claude-dts claude-rag --all --set dts   # a separate pool: Deep Tax Search vs not

The judges get what tax_judge.py gives them (question, key evidence, gold sections, answers labelled A, B, ... in a seeded
order, identical answers merged, no system names) and return correct / partial / incorrect per label into verdicts.json.
Answer texts paraphrase IRAS material, so they stay in .cache/. chat.gov.sg was asked too, but its terms of use forbid
benchmarking the service, so its results are excluded from every published output (`--exclude chat-gov-sg`).
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.tax_experiment import OUT, load_keys  # noqa: E402
from eval.tax_judge import SCORE, _final, _kappa, gold_text  # noqa: E402
from eval.tax_report import _fmt_diff, paired  # noqa: E402
from src.common import CACHE, read_jsonl  # noqa: E402
from src.tax.corpus import chunks, load_tax_questions  # noqa: E402

SAMPLE = OUT / "chatbot_sample.json"
BOTS = CACHE / "tax" / "chatbots"
JUDGE = CACHE / "tax" / "judge_chatbots"
SEED = 3415
PER_TYPE = {"natural": 19, "section_ref": 5, "old_number": 1}   # 25 of the 79 answerable test questions, by type
CLOSED_SYSTEM = ("You answer Singapore income tax questions for tax associates at accounting firms. Answer accurately and "
                 "concisely, citing the provisions of the Income Tax Act 1947 or the IRAS guidance you rely on. If you are not "
                 "sure of the answer, say so instead of guessing.")
# (system, where its answers are): `pipeline` rows come from the generation files of tax_generation.py / tax_rq12.py
PIPELINE = {"claude-rag": ("generation_per_question_claude.jsonl", "generation_answers_claude.jsonl", "teammate-improved@gemini"),
            "claude-dts": ("generation_per_question_claude.jsonl", "generation_answers_claude.jsonl", "R6y@gemini"),   # Deep Tax Search
            "qwen3-rag": ("generation_per_question_rq12.jsonl", "generation_answers_rq12.jsonl", "B0")}
SET = ""   # --set NAME: a separate judging pool, .cache/tax/judge_chatbots_NAME/ and *_NAME output files


def answerable_test() -> dict:
    return {q.id: q for q in load_tax_questions("heldout") if q.split == "test" and q.answerable}


def sample() -> None:
    if SAMPLE.exists():
        raise SystemExit(f"{SAMPLE} exists: the sample is fixed once chatbots have been asked")
    qs, rng, ids = answerable_test(), random.Random(SEED), []
    for t, n in PER_TYPE.items():
        ids += rng.sample(sorted(i for i, q in qs.items() if q.type == t), n)
    SAMPLE.write_text(json.dumps([dict(qid=i, type=qs[i].type, question=qs[i].question) for i in sorted(ids)], indent=1,
                                 ensure_ascii=False) + "\n", encoding="utf-8")
    print(len(ids), "questions ->", SAMPLE)


def sample_ids() -> list[str]:
    return [r["qid"] for r in json.loads(SAMPLE.read_text(encoding="utf-8"))]


def closed_book(all_questions: bool) -> None:
    from src.llm.claude import ClaudeChat, cost
    qs = answerable_test()
    ids = sorted(qs) if all_questions else sample_ids()
    chat, records = ClaudeChat(cache_name="tax-closed-book"), []
    path = BOTS / "claude-closed.jsonl"
    done = {r["qid"]: r for r in read_jsonl(path)} if path.exists() else {}
    BOTS.mkdir(parents=True, exist_ok=True)
    for i in ids:
        out = chat.generate(CLOSED_SYSTEM, qs[i].question)
        records.append(out)
        done[i] = dict(qid=i, text=out["text"], stop_reason=out["stop_reason"], served_by=out["served_by"],
                       output_tokens=out["usage"]["output_tokens"])
        print(f"  {i}: {out['stop_reason']}, {out['usage']['output_tokens']} output tokens{' (cached)' if out['cached'] else ''}",
              flush=True)
    path.write_text("".join(json.dumps(done[i], ensure_ascii=False) + "\n" for i in sorted(done)), encoding="utf-8")
    print(f"{len(ids)} answers -> {path}; ${cost(records):.2f} at list prices (cached ones included)")


def answers(system: str) -> dict[str, str | None]:
    """{qid: answer text, or None for a refusal} over the answerable test questions the system answered."""
    if system in PIPELINE:
        gen_file, text_file, condition = PIPELINE[system]
        gen = {r["qid"]: r for r in read_jsonl(OUT / gen_file) if r["qset"] == "heldout" and r["condition"] == condition}
        texts = {r["qid"]: r["text"] for r in read_jsonl(CACHE / "tax" / text_file)
                 if r["qset"] == "heldout" and r["condition"] == condition}
        return {i: None if g["refused"] else texts[i].strip() for i, g in gen.items()}
    # a chatbot's "please rephrase" fallback or a decline to answer counts as no answer, like a refusal
    return {r["qid"]: None if r.get("non_answer") or not r["text"].strip() else r["text"].strip()
            for r in read_jsonl(BOTS / f"{system}.jsonl")}


def prep(n_batches: int, systems: list[str], all_questions: bool) -> None:
    """A system that answered only the sample (the chatbots) is graded on the sample; the others on every question."""
    if (JUDGE / "verdicts.json").exists():
        raise SystemExit(f"{JUDGE} already has verdicts: move them aside first, prep would relabel the answers they grade")
    qs = answerable_test()
    ids = sorted(qs) if all_questions else sample_ids()
    got = {s: answers(s) for s in systems}
    for s in systems:
        missing = [i for i in ids if i not in got[s]]
        external = s not in PIPELINE and s != "claude-closed"   # only the chatbots may cover just the sample
        if missing and not (external and all_questions and set(sample_ids()) <= set(got[s])):
            raise SystemExit(f"{s}: no answer for {len(missing)} question(s), e.g. {missing[:3]}")
        if missing:
            print(f"{s}: graded on the {len(sample_ids())}-question sample only")
    evidence = {r["id"]: r for r in read_jsonl(CACHE / "tax" / "heldout_evidence.jsonl")}
    structured = chunks("structured")
    rng, items, key = random.Random(SEED), [], {}
    for i in ids:
        texts: dict[str, list[str]] = {}
        for s in systems:
            if i in got[s]:
                texts.setdefault(got[s][i] or "REFUSED", []).append(s)
        distinct = [t for t in texts if t != "REFUSED"]
        rng.shuffle(distinct)
        labels = {chr(ord("A") + k): t for k, t in enumerate(distinct)}
        key[i] = dict({lab: texts[t] for lab, t in labels.items()}, REFUSED=texts.get("REFUSED", []))
        ev = evidence.get(i, {})
        if distinct:
            items.append(dict(qid=i, question=qs[i].question, key_evidence=ev.get("evidence", ""),
                              gold_sources=[gold_text(structured, d, u, ev.get("evidence_chunk_id", "")) for d, u in sorted(qs[i].gold_units)],
                              answers=[dict(label=lab, text=t) for lab, t in labels.items()]))
    JUDGE.mkdir(parents=True, exist_ok=True)
    per = -(-len(items) // n_batches)
    for b in range(n_batches):
        (JUDGE / f"batch_{b}.json").write_text(json.dumps(items[b * per:(b + 1) * per], indent=1, ensure_ascii=False), encoding="utf-8")
    (JUDGE / "key.json").write_text(json.dumps(dict(systems=systems, questions=ids, key=key), indent=1), encoding="utf-8")
    print(len(items), "questions;", sum(len(it["answers"]) for it in items), "distinct answers;", n_batches, "batches of", per)


def _rows(key: dict, systems: list[str], grade) -> tuple[list[dict], list]:
    """Per (question, system) rows; grade(qid, label) is the final verdict, or None if that answer was not graded."""
    rows, missing = [], []
    for qid, labels in key.items():
        for s in systems:
            lab = next((lab for lab, ss in labels.items() if s in ss), None)
            if lab is None:   # a chatbot, not asked this question (outside the sample)
                continue
            verdict = None
            if lab != "REFUSED":
                verdict = grade(qid, lab)
                if verdict is None:
                    missing.append((qid, lab))
                    continue
            rows.append(dict(qid=qid, condition=s, answered=float(verdict is not None), verdict=verdict,
                             correct_all=SCORE[verdict] if verdict else 0.0, strict_all=float(verdict == "correct"),
                             wrong_all=float(verdict == "incorrect")))
    return rows, missing


def _tables(rows: list[dict], systems: list[str], n_questions: int) -> list[str]:
    """The sample table, then the all-questions table for the systems that answered every question; each system paired
    with the first."""
    lines, sample, every = [], set(sample_ids()), {r["qid"] for r in rows}
    views = [(f"The {len(sample)}-question sample (every system)", sample)]
    if every != sample:
        views.append((f"All {n_questions} questions (the systems that answered all of them)", every))
    for title, qids in views:
        here = [s for s in systems if {r["qid"] for r in rows if r["condition"] == s} >= qids]
        if len(here) < 2:
            continue
        sub = [r for r in rows if r["qid"] in qids]
        lines += [f"## {title}", "", "| System | Answered | Correct / partial / incorrect | Correct (all) | Fully correct (all) | "
                  "Wrong (all) |", "|---|---|---|---|---|---|"]
        for s in here:
            rs = [r for r in sub if r["condition"] == s]
            cnt = Counter(r["verdict"] for r in rs if r["verdict"])
            lines.append(f"| `{s}` | {int(sum(r['answered'] for r in rs))}/{len(rs)} | {cnt['correct']} / {cnt['partial']} / "
                         f"{cnt['incorrect']} | {np.mean([r['correct_all'] for r in rs]):.3f} | "
                         f"{np.mean([r['strict_all'] for r in rs]):.3f} | {np.mean([r['wrong_all'] for r in rs]):.3f} |")
        lines += ["", "Paired over these questions: mean A − B [95% bootstrap CI], Wilcoxon p, questions A higher / lower.", "",
                  "| A | B | Metric | Mean A − B [95% CI] | Wilcoxon p | A higher / lower |", "|---|---|---|---|---|---|"]
        for b in here[1:]:
            for m, label in [("correct_all", "correct (all)"), ("wrong_all", "wrong (all)")]:
                s_, p, wl = _fmt_diff(paired(sub, here[0], b, m))
                lines.append(f"| `{here[0]}` | `{b}` | {label} | {s_} | {p} | {wl} |")
        lines.append("")
    return lines


def _first_round(exclude: list[str]):
    """(systems kept, key, final grade per (qid, label), judge-1/judge-2 pairs over the kept systems' answers)"""
    meta = json.loads((JUDGE / "key.json").read_text(encoding="utf-8"))
    systems, key = [s for s in meta["systems"] if s not in exclude], meta["key"]
    graded = {}
    for b in json.loads((JUDGE / "verdicts.json").read_text(encoding="utf-8")):
        for role in ("judge1", "judge2", "tiebreak"):
            for v in b[role]:
                graded.setdefault((v["qid"], v["label"]), {})[role] = v["verdict"]
    kept = {(q, lab) for q, labels in key.items() for lab, ss in labels.items() if lab != "REFUSED" and set(ss) & set(systems)}
    final = {k: _final(g.get("judge1"), g.get("judge2"), g.get("tiebreak")) for k, g in graded.items() if k in kept}
    pairs = [(g["judge1"], g["judge2"]) for k, g in graded.items() if k in kept and "judge1" in g and "judge2" in g]
    return systems, key, final, pairs


def score(exclude: list[str]) -> None:
    systems, key, final, pairs = _first_round(exclude)
    rows, missing = _rows(key, systems, lambda q, lab: final.get((q, lab)))
    with open(OUT / f"chatbot_judge_per_question{SET}.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r) + "\n" for r in rows)
    lines = ["# Claude in the tax RAG against existing tax chatbots: blind correctness judging", "",
             f"{len(key)} answerable held-out test questions, {len(final)} distinct answers graded by two LLM judges (opposite "
             f"reading orders, system hidden), a third on each disagreement. Agreement between the first two: "
             f"{np.mean([a == b for a, b in pairs]):.2f}, Cohen's κ {_kappa(pairs):.2f}"
             + (f". Not graded (left out): {len(missing)}." if missing else "."), "",
             "Correct (all): correct 1, partial 0.5, incorrect or no answer 0, over every question. Wrong (all): share answered "
             "incorrectly (lower is better). A chatbot's \"please rephrase\" fallback or a decline counts as no answer.", ""]
    lines += _tables(rows, systems, len(key))
    (OUT / f"chatbot_summary{SET}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def regrade_prep() -> None:
    """The sample's answers, as the first round labelled them, in two batches for a skeptical re-grade."""
    items = sorted((it for p in sorted(JUDGE.glob("batch_*.json")) for it in json.loads(p.read_text(encoding="utf-8"))
                    if it["qid"] in set(sample_ids())), key=lambda it: it["qid"])
    half = (len(items) + 1) // 2
    for i, part in enumerate([items[:half], items[half:]]):
        (JUDGE / f"regrade_{i}.json").write_text(json.dumps(part, indent=1, ensure_ascii=False), encoding="utf-8")
    print(len(items), "questions,", sum(len(it["answers"]) for it in items), "answers -> regrade_0.json, regrade_1.json")


def regrade_score(exclude: list[str]) -> None:
    """regrade_verdicts.json ([{batch, judge, verdicts}], two judges per batch) -> chatbot_regrade_summary.md: the lower
    grade where the two differ, against the first round's."""
    systems, key, first, _ = _first_round(exclude)
    key = {q: key[q] for q in sample_ids()}
    two: dict = {}
    for b in json.loads((JUDGE / "regrade_verdicts.json").read_text(encoding="utf-8")):
        for v in b["verdicts"]:
            two.setdefault((v["qid"], v["label"]), {})[b["judge"]] = v["verdict"]
    kept = {(q, lab) for q, labels in key.items() for lab, ss in labels.items() if lab != "REFUSED" and set(ss) & set(systems)}
    pairs = [(g[1], g[2]) for k, g in two.items() if k in kept and 1 in g and 2 in g]
    rows, missing = _rows(key, systems, lambda q, lab: _final(two.get((q, lab), {}).get(1), two.get((q, lab), {}).get(2), None)
                          if (q, lab) in two else None)
    before, _ = _rows(key, systems, lambda q, lab: first.get((q, lab)))
    old = {(r["qid"], r["condition"]): r["verdict"] for r in before}
    changed = Counter(r["condition"] for r in rows if r["verdict"] != old.get((r["qid"], r["condition"])))
    lines = ["# Skeptical re-grade of the sample", "",
             f"{len(kept)} distinct answers of the {len(key)}-question sample re-graded blind by two fresh judges (told that some "
             f"systems are better than others, to list every claim and recompute every figure). Agreement {np.mean([a == b for a, b in pairs]):.2f}, "
             f"Cohen's κ {_kappa(pairs):.2f}; the lower grade where they differ"
             + (f". Not graded (left out): {len(missing)}." if missing else "."),
             f"Grades changed from the first round: {sum(changed.values())} of {len(rows)} ({dict(changed)}).", ""]
    lines += _tables(rows, systems, len(key))
    (OUT / f"chatbot_regrade_summary{SET}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("stage", choices=["sample", "closed-book", "prep", "score", "regrade-prep", "regrade-score"])
    ap.add_argument("rest", nargs="*", help="prep: the number of batches, then the systems (the first is compared with the rest)")
    ap.add_argument("--all", action="store_true", help="every answerable test question instead of the sample")
    ap.add_argument("--set", default="", help="a separate judging pool (its own batches, key and outputs)")
    ap.add_argument("--exclude", nargs="*", default=[], help="score, regrade-score: leave these systems out of the outputs")
    args = ap.parse_args()
    global JUDGE, SET
    if args.set:
        SET = "_" + args.set
        JUDGE = JUDGE.with_name(JUDGE.name + SET)
    if args.stage == "sample":
        sample()
    elif args.stage == "closed-book":
        load_keys()
        closed_book(args.all)
    elif args.stage == "prep":
        prep(int(args.rest[0]), args.rest[1:], args.all)
    elif args.stage == "score":
        score(args.exclude)
    elif args.stage == "regrade-prep":
        regrade_prep()
    else:
        regrade_score(args.exclude)


if __name__ == "__main__":
    main()
