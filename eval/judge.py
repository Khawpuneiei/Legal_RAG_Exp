"""LLM-as-judge for the reviewer note (plan section 7, metric hierarchy level 2) and the human spot-check export.

Judge: llama3.1:8b (a different model family from the qwen2.5 generator, to reduce self-preference). Binary rubric,
reasons before verdicts, condition names hidden, one note at a time (pointwise, so no position bias), reference-guided
(the judge sees the request and the reference problems and route). Length bias is reported as the Spearman correlation
between note length and judge score.

  python eval/judge.py                 # judge a seeded 20% sample (18 test requests) for every condition, seed 1
  python eval/judge.py --kappa FILE    # Cohen's kappa between the judge and a human-labelled spot-check CSV

Outputs eval/results/judge/: judge_scores.jsonl, summary.md, human_spotcheck.csv (to be labelled by a team member).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval.metrics.retrieval_metrics import bootstrap_ci  # noqa: E402
from src.common import JsonCache, read_jsonl  # noqa: E402
from src.drafting.schema import extract_json  # noqa: E402
from src.llm.ollama import OllamaLLM  # noqa: E402

OUT = ROOT / "eval" / "results" / "judge"
CONDITIONS = ["S0", "S1", "S2", "S3", "S4", "S5", "S0s", "H-det", "H0", "H1", "H2", "H3", "H4", "H3b"]
QUESTIONS = {
    "q1_parties": "Does the note correctly state the agreement type and the counterparty?",
    "q2_requests": "Does the note mention every special request the colleague made (as listed in the reference)?",
    "q3_problems": "Does the note mention every problem in the reference problem list (or say there are none, if the list is empty)?",
    "q4_route": "Does the note state a routing decision that matches the reference route?",
    "q5_no_invention": "Is every fact in the note supported by the request (no invented names, dates, amounts or terms)?",
}
JUDGE_SYSTEM = "You are a strict senior lawyer grading a junior's note. You answer only with JSON."
JUDGE_PROMPT = """<request>
{request}
</request>
<reference>
Special requests: {asks}
Problems: {problems}
Route: {route}
</reference>
<note>
{note}
</note>

Grade the note. For each question first give a short reason, then true or false.
{questions}
Return JSON: {{"reasons": "<one or two sentences per question>", {keys}}}"""


def sample_items(n: int = 18, seed: int = 11) -> list[dict]:
    items = [r for r in read_jsonl(ROOT / "data" / "synthetic" / "intake.jsonl") if r["split"] == "test"]
    rng = random.Random(seed)
    return sorted(rng.sample(items, n), key=lambda r: r["request_id"])


def blind_id(cond: str, rid: str) -> str:
    return hashlib.sha256(f"{cond}|{rid}".encode()).hexdigest()[:8]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--kappa")
    a = ap.parse_args()
    if a.kappa:
        return kappa(a.kappa)
    runs = JsonCache("exp12-runs")
    judge = OllamaLLM("llama3.1:8b", num_ctx=8192, cache_name="judge")
    items = sample_items()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    qtext = "\n".join(f"- {k}: {q}" for k, q in QUESTIONS.items())
    keys = ", ".join(f'"{k}": true|false' for k in QUESTIONS)
    for it in items:
        problems = "; ".join(d["type"] + (f" ({d['field']})" if d.get("field") else "") for d in it["defects"]) or "none"
        asks = ", ".join(a.replace("_", " ") for a in it["asks"] + it["missing_asks"]) or "none"
        for cond in CONDITIONS:
            r = runs.get(f"v1|{cond}|{it['request_id']}|1")
            if r is None:
                continue
            note = (r["final"].get("reviewer_note") or "").strip() or "(empty)"
            out = judge.generate(JUDGE_PROMPT.format(request=it["text"], asks=asks, problems=problems, route=it["gold_route"], note=note,
                                                     questions=qtext, keys=keys), system=JUDGE_SYSTEM, temperature=0.0, seed=0, json_mode=True, max_tokens=400)
            data = extract_json(out["text"]) or {}
            verdicts = {k: bool(data.get(k)) if isinstance(data.get(k), bool) else str(data.get(k)).lower() == "true" for k in QUESTIONS}
            rows.append(dict(id=blind_id(cond, it["request_id"]), condition=cond, request_id=it["request_id"], note=note, words=len(note.split()),
                             score=sum(verdicts.values()) / len(verdicts), reasons=str(data.get("reasons", ""))[:800], **verdicts))
    with open(OUT / "judge_scores.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    lines = ["# LLM judge: reviewer note quality", "",
             f"Judge llama3.1:8b (generator family: qwen2.5), {len(items)} test requests sampled with a fixed seed (20%), seed-1 runs, "
             "binary rubric, reasons before verdicts, condition names hidden. Score = share of the five questions answered true. "
             "Brackets: 95% bootstrap CIs over requests. Length bias: Spearman rho between note length (words) and score.", "",
             "| Condition | judge score | " + " | ".join(QUESTIONS) + " | mean words | length rho |", "|---|---|" + "---|" * len(QUESTIONS) + "---|---|"]
    for cond in CONDITIONS:
        rs = [r for r in rows if r["condition"] == cond]
        if not rs:
            continue
        mean, lo, hi = bootstrap_ci([r["score"] for r in rs])
        rho = spearmanr([r["words"] for r in rs], [r["score"] for r in rs]).statistic if len({r["words"] for r in rs}) > 1 else float("nan")
        lines.append(f"| {cond} | {mean:.2f} [{lo:.2f}, {hi:.2f}] | " + " | ".join(f"{np.mean([r[k] for r in rs]):.2f}" for k in QUESTIONS)
                     + f" | {np.mean([r['words'] for r in rs]):.0f} | {rho:.2f} |")
    lines += ["", "Human spot-check: `human_spotcheck.csv` holds the same notes with the judge verdicts hidden behind blind ids. A team member "
              "fills the five human_* columns (1/0); then `python eval/judge.py --kappa eval/results/judge/human_spotcheck.csv` reports "
              "Cohen's kappa between judge and human (plan section 7). This step needs a person and has not been done."]
    (OUT / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with open(OUT / "human_spotcheck.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "request_id", "request_text", "reference_problems", "reference_route", "note"] + [f"human_{k}" for k in QUESTIONS])
        by_rid = {it["request_id"]: it for it in items}
        shuffled = rows[:]
        random.Random(3).shuffle(shuffled)
        for r in shuffled:
            it = by_rid[r["request_id"]]
            w.writerow([r["id"], r["request_id"], it["text"], "; ".join(d["type"] for d in it["defects"]) or "none", it["gold_route"], r["note"]] + [""] * len(QUESTIONS))
    print("\n".join(lines))


def kappa(path: str) -> None:
    from sklearn.metrics import cohen_kappa_score
    judged = {r["id"]: r for r in read_jsonl(OUT / "judge_scores.jsonl")}
    h, j = [], []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            for k in QUESTIONS:
                v = row.get(f"human_{k}", "").strip()
                if v in ("0", "1") and row["id"] in judged:
                    h.append(int(v))
                    j.append(int(judged[row["id"]][k]))
    if not h:
        print("no human labels found")
        return
    print(f"{len(h)} labelled verdicts, agreement {np.mean(np.array(h) == np.array(j)):.3f}, Cohen's kappa {cohen_kappa_score(h, j):.3f}")


if __name__ == "__main__":
    main()
