"""Blind correctness judging of the TaxRAG answers on the held-out test split.

`prep` writes batches for the judges: each answerable question with its key evidence, the gold sections (each cut
at MAX_SECTION_CHARS, the evidence chunk first) and the distinct answers of the chosen configurations, labelled A,
B, ... in a seeded random order (identical answers merged, refusals left out). The judges (LLM agents, two per batch
reading in opposite orders, a third on every disagreement) return correct / partial / incorrect per label into
verdicts.json; `score` maps the labels back. `add` grades a configuration run later without relabelling the graded
ones: an answer identical to a graded one takes its label, the others get new labels in new batches.

    python eval/tax_judge.py prep 6 teammate-improved@gemini R6x@gemini ...   # -> .cache/tax/judge/ (IRAS text, not in the repo)
    python eval/tax_judge.py add 2 R6y@gemini   # -> .cache/tax/judge/batch_add1_<i>.json; their verdicts go into verdicts.json too
    python eval/tax_judge.py score    # .cache/tax/judge/verdicts.json -> eval/results/tax/judge_per_question.jsonl, judge_summary.md
    python eval/tax_judge.py prep 3 teammate-improved@gemini R6y@gemini --suffix _gemini   # the Gemini Flash answers:
                                      # .cache/tax/judge_gemini/, then judge_per_question_gemini.jsonl, judge_summary_gemini.md
Needs .cache/tax/heldout_evidence.jsonl, which scripts/build_tax_questions.py writes from the audited drafts.
"""
from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.tax_experiment import OUT  # noqa: E402
from eval.tax_report import _fmt_diff, paired  # noqa: E402
from src.common import CACHE, read_jsonl  # noqa: E402
from src.tax.corpus import chunks, load_tax_questions  # noqa: E402

JUDGE = CACHE / "tax" / "judge"
GEN = OUT / "generation_per_question.jsonl"
ANSWERS = CACHE / "tax" / "generation_answers.jsonl"
SUFFIX = ""   # "_gemini" (--suffix): the answers of `tax_generation.py --model gemini`, in their own files
SPLIT = "test"   # --split dev: the held-out dev split, judged into judge{SUFFIX}-dev and *{SUFFIX}-dev outputs
TAG = ""         # SUFFIX plus "-dev" for the dev split: the output files' suffix
MAX_SECTION_CHARS = 9000
SCORE = {"correct": 1.0, "partial": 0.5, "incorrect": 0.0}
# (A, B, question): paired over the held-out test split's answerable questions
COMPARISONS = [
    ("R6x@gemini", "teammate-improved@gemini", "A* dependencies in place of his expansion, his deployed setup otherwise"),
    ("R6y@gemini", "teammate-improved@gemini", "dependency-only A* in place of his expansion, his deployed setup otherwise"),
    ("R6d@gemini", "teammate-improved@gemini", "A* evidence in place of his whole context, on his Gemini ranking"),
    ("R5@budget", "teammate-improved@bge-m3", "Experiment 3 retrieval (R5) vs his `improved`, same local embedder"),
    ("R5+expand", "teammate-improved@bge-m3", "R5 vs his `improved`, same local embedder and context layout (hits + his expansion)"),
    ("R5@budget", "R5+expand", "his one-hop expansion removed, R5 hits"),
    ("R6x", "R5+expand", "A* dependencies vs his expansion, after the R5 hits"),
    ("R5@budget", "teammate-improved@gemini", "the local pipeline (no API key) vs his deployed Gemini retrieval"),
    ("teammate-improved@gemini", "teammate-improved@bge-m3", "his `improved`: Gemini vs the local embedder"),
]


def _questions():
    return {q.id: q for q in load_tax_questions("heldout") if q.split == SPLIT and q.answerable}


def gold_text(structured, doc: str, unit: str, key_chunk: str) -> str:
    if doc == "ITA":
        cs = [c for c in structured if c.doc_type == "act" and c.section == unit]
        cs.sort(key=lambda c: (c.chunk_id != key_chunk, c.char_start))   # the evidence chunk first, then document order
        title = f"Income Tax Act 1947, section {unit}"
    else:
        cs = [c for c in structured if c.chunk_id.split(":", 1)[0] == doc and c.chunk_id.split(":", 1)[1].split("#")[0] == unit]
        cs.sort(key=lambda c: c.char_start)
        title = f"{cs[0].doc_title if cs else doc}, paragraph {unit}"
    text, out = "", []
    for c in cs:
        piece = f"[{c.cite or c.chunk_id}] {c.text.strip()}"
        if len(text) + len(piece) > MAX_SECTION_CHARS:
            out.append("[... rest of the section omitted ...]")
            break
        out.append(piece)
        text += piece
    return title + "\n" + "\n\n".join(out)


def prep(n_batches: int, configs: list[str]) -> None:
    if (JUDGE / "verdicts.json").exists():
        raise SystemExit(f"{JUDGE} already has verdicts: move them aside first, prep would relabel the answers they grade")
    JUDGE.mkdir(parents=True, exist_ok=True)
    qs = _questions()
    evidence = {r["id"]: r for r in read_jsonl(CACHE / "tax" / "heldout_evidence.jsonl")}
    texts_by = {(r["qid"], r["condition"]): r["text"] for r in read_jsonl(ANSWERS) if r["qset"] == "heldout"}
    gen = {(r["qid"], r["condition"]): r for r in read_jsonl(GEN) if r["qset"] == "heldout"}
    structured = chunks("structured")
    items, key, rng = [], {}, random.Random(3415)
    for qid in sorted(qs):
        q, ev, texts = qs[qid], evidence.get(qid, {}), {}
        for c in configs:
            if (qid, c) not in gen:
                raise SystemExit(f"no answer for {qid} {c}")
            t = "REFUSED" if gen[(qid, c)]["refused"] else texts_by[(qid, c)].strip()
            texts.setdefault(t, []).append(c)
        distinct = [t for t in texts if t != "REFUSED"]
        rng.shuffle(distinct)
        labels = {chr(ord("A") + i): t for i, t in enumerate(distinct)}
        key[qid] = dict({lab: texts[t] for lab, t in labels.items()}, REFUSED=texts.get("REFUSED", []))
        if distinct:
            items.append(dict(qid=qid, question=q.question, key_evidence=ev.get("evidence", ""),
                              gold_sources=[gold_text(structured, d, u, ev.get("evidence_chunk_id", "")) for d, u in sorted(q.gold_units)],
                              answers=[dict(label=lab, text=t) for lab, t in labels.items()]))
    per = -(-len(items) // n_batches)
    for b in range(n_batches):
        (JUDGE / f"batch_{b}.json").write_text(json.dumps(items[b * per:(b + 1) * per], indent=1, ensure_ascii=False), encoding="utf-8")
    (JUDGE / "key.json").write_text(json.dumps(dict(configs=configs, key=key), indent=1), encoding="utf-8")
    print(len(items), "questions with answers;", sum(len(i["answers"]) for i in items), "distinct answers;", n_batches, "batches of", per)


def add(n_batches: int, configs: list[str]) -> None:
    meta = json.loads((JUDGE / "key.json").read_text(encoding="utf-8"))
    qs = _questions()
    evidence = {r["id"]: r for r in read_jsonl(CACHE / "tax" / "heldout_evidence.jsonl")}
    texts_by = {(r["qid"], r["condition"]): r["text"] for r in read_jsonl(ANSWERS) if r["qset"] == "heldout"}
    gen = {(r["qid"], r["condition"]): r for r in read_jsonl(GEN) if r["qset"] == "heldout"}
    structured = chunks("structured")
    graded: dict[tuple[str, str], str] = {}   # (qid, answer text) -> its label, from every batch written so far
    for path in JUDGE.glob("batch*.json"):
        for item in json.loads(path.read_text(encoding="utf-8")):
            for a in item["answers"]:
                graded[(item["qid"], a["text"])] = a["label"]
    round_ = 1 + len({p.stem.split("_")[1] for p in JUDGE.glob("batch_add*_*.json")})
    items = []
    for qid in sorted(qs):
        q, ev, labels, new = qs[qid], evidence.get(qid, {}), meta["key"][qid], {}
        for c in configs:
            if (qid, c) not in gen:
                raise SystemExit(f"no answer for {qid} {c}")
            t = "REFUSED" if gen[(qid, c)]["refused"] else texts_by[(qid, c)].strip()
            if t == "REFUSED":
                label = "REFUSED"
            elif (qid, t) in graded:
                label = graded[(qid, t)]
            else:   # a new answer: the next free label
                label = chr(ord("A") + sum(1 for k in labels if k != "REFUSED"))
                new[label], graded[(qid, t)] = t, label
            labels.setdefault(label, []).append(c)
        if new:
            items.append(dict(qid=qid, question=q.question, key_evidence=ev.get("evidence", ""),
                              gold_sources=[gold_text(structured, d, u, ev.get("evidence_chunk_id", "")) for d, u in sorted(q.gold_units)],
                              answers=[dict(label=lab, text=t) for lab, t in new.items()]))
    meta["configs"] += [c for c in configs if c not in meta["configs"]]
    per = -(-len(items) // n_batches)
    for b in range(n_batches):
        (JUDGE / f"batch_add{round_}_{b}.json").write_text(json.dumps(items[b * per:(b + 1) * per], indent=1, ensure_ascii=False),
                                                         encoding="utf-8")
    (JUDGE / "key.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(len(items), "questions with new answers;", sum(len(i["answers"]) for i in items), "new distinct answers;", n_batches,
          "batches of", per)


def _final(v1: str | None, v2: str | None, v3: str | None) -> str:
    """Both judges agree, or the median of the three grades."""
    if v1 and v1 == v2:
        return v1
    got = sorted((SCORE[v] for v in (v1, v2, v3) if v), reverse=True)
    m = got[len(got) // 2] if len(got) != 2 else min(got)   # two grades only (no tie-break): the lower one
    return {s: v for v, s in SCORE.items()}[m]


def _kappa(pairs: list[tuple[str, str]]) -> float:
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in SCORE) / n ** 2
    return (po - pe) / (1 - pe)


def score() -> None:
    meta = json.loads((JUDGE / "key.json").read_text(encoding="utf-8"))
    configs, key = meta["configs"], meta["key"]
    graded = {}
    for b in json.loads((JUDGE / "verdicts.json").read_text(encoding="utf-8")):
        for role in ("judge1", "judge2", "tiebreak"):
            for v in b[role]:
                graded.setdefault((v["qid"], v["label"]), {})[role] = v["verdict"]
    pairs = [(g["judge1"], g["judge2"]) for g in graded.values() if "judge1" in g and "judge2" in g]
    rows, missing = [], []
    for qid, labels in key.items():
        for c in configs:
            lab = next((lab for lab, cs in labels.items() if c in cs), None)
            if lab == "REFUSED":
                verdict = None
            else:
                g = graded.get((qid, lab), {})
                if not g:
                    missing.append((qid, lab))
                    continue
                verdict = _final(g.get("judge1"), g.get("judge2"), g.get("tiebreak"))
            rows.append(dict(qid=qid, condition=c, answered=float(verdict is not None), verdict=verdict,
                             correct_all=SCORE[verdict] if verdict else 0.0, strict_all=float(verdict == "correct"),
                             wrong_all=float(verdict == "incorrect")))
    with open(OUT / f"judge_per_question{TAG}.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    n_q = len(key)
    model = {"_gemini": "gemini-3.8-flash, his app's fallback", "_groq": "gpt-oss-120b, his app's model",
             "_qwen3-8b": "qwen3:8b, local, reasoning", "_rq12": "qwen3:8b, local, reasoning; RQ1 and RQ2"}.get(SUFFIX, "qwen2.5:7b")
    lines = [f"# TaxRAG answers ({model}): blind correctness judging (held-out {SPLIT} split)", "",
             f"{n_q} answerable questions, {len(graded)} distinct answers graded by two independent LLM judges (opposite reading "
             f"orders, configuration hidden), a third on each disagreement; the grade is the agreed one or the median of three. "
             f"Agreement between the first two: {np.mean([a == b for a, b in pairs]):.2f}, Cohen's κ {_kappa(pairs):.2f}"
             + (f". Not graded (left out): {len(missing)}." if missing else "."), "",
             "Correct (all): correct 1, partial 0.5, incorrect or refused 0, over every answerable question. Fully correct (all): "
             "only `correct` counts. Wrong (all): share of questions answered incorrectly (lower is better).", "",
             "| Configuration | Answered | Correct / partial / incorrect | Correct (all) | Fully correct (all) | Wrong (all) |",
             "|---|---|---|---|---|---|"]
    for c in configs:
        rs = [r for r in rows if r["condition"] == c]
        cnt = Counter(r["verdict"] for r in rs if r["verdict"])
        lines.append(f"| `{c}` | {int(sum(r['answered'] for r in rs))}/{len(rs)} | {cnt['correct']} / {cnt['partial']} / {cnt['incorrect']} | "
                     f"{np.mean([r['correct_all'] for r in rs]):.3f} | {np.mean([r['strict_all'] for r in rs]):.3f} | "
                     f"{np.mean([r['wrong_all'] for r in rs]):.3f} |")
    lines += ["", "Paired over the answerable questions: mean A − B [95% bootstrap CI], Wilcoxon p, questions A better / worse. "
              "**Bold**: the CI excludes 0. For wrong (all), a negative difference favours A.", "",
              "| A | B | Question | Metric | Mean A − B [95% CI] | Wilcoxon p | A higher / lower |", "|---|---|---|---|---|---|---|"]
    comparisons = COMPARISONS
    if SUFFIX == "_rq12":   # the RQ1/RQ2 conditions' own pairs (docs/taxrag-rq12-protocol.md)
        from eval.tax_rq12 import COMPARISONS as comparisons
    for a, b, what in [(a, b, w) for a, b, w in comparisons if a in configs and b in configs]:
        for m, label in [("correct_all", "correct (all)"), ("strict_all", "fully correct (all)"), ("wrong_all", "wrong (all)")]:
            s, p, wl = _fmt_diff(paired(rows, a, b, m))
            lines.append(f"| `{a}` | `{b}` | {what} | {label} | {s} | {p} | {wl} |")
    if SUFFIX == "_rq12":   # the protocol's three primary comparisons, Holm-adjusted (step-down over their Wilcoxon p)
        from eval.tax_rq12 import PRIMARY
        found = [(a, b, paired(rows, a, b, "correct_all")) for a, b in PRIMARY if a in configs and b in configs]
        if found:
            order = sorted(range(len(found)), key=lambda i: (np.nan_to_num(found[i][2]["p"], nan=1.0) if found[i][2] else 1.0))
            adjusted, running = {}, 0.0
            for rank, i in enumerate(order):
                p = found[i][2]["p"] if found[i][2] and not np.isnan(found[i][2]["p"]) else 1.0
                running = max(running, min(1.0, (len(found) - rank) * p))
                adjusted[i] = running
            lines += ["", "Primary comparisons (protocol): correct (all), Wilcoxon p and its Holm adjustment over the three.", "",
                      "| A | B | Mean A − B [95% CI] | Wilcoxon p | Holm p |", "|---|---|---|---|---|"]
            for i, (a, b, c) in enumerate(found):
                s, p, _ = _fmt_diff(c)
                lines.append(f"| `{a}` | `{b}` | {s} | {p} | {adjusted[i]:.3f} |")
    (OUT / f"judge_summary{TAG}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    if "--suffix" in sys.argv:
        i = sys.argv.index("--suffix")
        SUFFIX = sys.argv[i + 1]
        del sys.argv[i:i + 2]
        JUDGE = CACHE / "tax" / f"judge{SUFFIX}"
        GEN = OUT / f"generation_per_question{SUFFIX}.jsonl"
        ANSWERS = CACHE / "tax" / f"generation_answers{SUFFIX}.jsonl"
    TAG = SUFFIX
    if "--split" in sys.argv:
        i = sys.argv.index("--split")
        SPLIT = sys.argv[i + 1]
        del sys.argv[i:i + 2]
        if SPLIT == "dev":
            TAG = SUFFIX + "-dev"
            JUDGE = CACHE / "tax" / f"judge{TAG}"
    if sys.argv[1:2] == ["prep"]:
        prep(int(sys.argv[2]), sys.argv[3:])
    elif sys.argv[1:2] == ["add"]:
        add(int(sys.argv[2]), sys.argv[3:])
    elif sys.argv[1:2] == ["score"]:
        score()
    else:
        raise SystemExit(__doc__)
