"""Calibrate and evaluate the configuration that is actually deployed (free tier: Supabase gte-small hybrid search,
rules mode, no LLM), so the demo's quality is measured rather than assumed.

1. Calibrate on the dev split: the similarity-to-relevance mapping (lo, hi) and the A* abstention cost tau,
   with the same objective as eval/exp12.py --tune. Writes configs/search_calibration.json.
2. Evaluate on the frozen test split:
   - retrieval: nDCG@10 / Recall@5 of the whole-request query against the graded gold clauses (comparable to Exp 3);
   - end to end: the production engine (src/drafting/engine.py, rules mode) scored with the Exp 2 metrics.
   Writes eval/results/deployed/summary.json and summary.md.

Usage:  python eval/deployed_eval.py        (needs network access to the Supabase project in configs/deployments/vercel.env)
"""
from __future__ import annotations

import itertools
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("VERCEL", "1")  # load the public demo defaults (Supabase URL and publishable keys)

from eval.metrics.drafting_metrics import ask_gold, score  # noqa: E402
from eval.metrics.retrieval_metrics import bootstrap_ci  # noqa: E402
from src.agreement.library import load_library  # noqa: E402
from src.app.config import settings  # noqa: E402
from src.app.search import SupabaseSearch, _relevance  # noqa: E402
from src.common import read_jsonl  # noqa: E402
from src.drafting.assembly import astar_assign, rule_requirements  # noqa: E402
from src.drafting.engine import make_draft  # noqa: E402

OUT = ROOT / "eval" / "results" / "deployed"


def items(split: str) -> list[dict]:
    return [r for r in read_jsonl(ROOT / "data" / "synthetic" / "intake.jsonl") if r["split"] == split]


def ndcg(ranked: list[str], graded: dict[str, int], k: int = 10) -> float:
    dcg = sum((2 ** graded.get(c, 0) - 1) / math.log2(i + 2) for i, c in enumerate(ranked[:k]))
    ideal = sorted(graded.values(), reverse=True)[:k]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg else float("nan")


def recall(ranked: list[str], graded: dict[str, int], k: int = 5, rel: int = 2) -> float:
    gold = {c for c, g in graded.items() if g >= rel}
    return len(gold & set(ranked[:k])) / len(gold) if gold else float("nan")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    s = settings()
    search = SupabaseSearch(s.supabase_url, s.supabase_anon_jwt, s.supabase_key)
    lib = load_library()
    OUT.mkdir(parents=True, exist_ok=True)

    # ---- 1. calibration on dev
    prepared = []
    for it in items("dev"):
        reqs = rule_requirements(it["text"])
        raw = [[h for h in search.search(q, k=8, agreement_type=it["agreement_type"]) if h.get("variant") != "definition"][:5] for q in reqs]
        prepared.append((it, raw))
    best = None
    for lo, hi, tau in itertools.product([0.70, 0.74, 0.78, 0.80, 0.82], [0.86, 0.88, 0.90, 0.92, 0.95], [round(x, 2) for x in np.arange(0.3, 1.01, 0.05)]):
        if hi <= lo:
            continue
        vals = []
        for it, raw in prepared:
            cands = [[dict(h, relevance=_relevance(h["score"], lo, hi)) for h in cs] for cs in raw]
            assign, _ = astar_assign(lib, cands, tau)
            cited = [c for c in assign if c]
            asks = it["asks"]
            rec = (sum(1 for a in asks if set(cited) & ask_gold(lib, it["agreement_type"], a)) / len(asks)) if asks else 1.0
            gold_any = {c for c, g in it["gold_clauses"].items() if g >= 2}
            wrong = sum(1 for c in cited if c not in gold_any) / max(1, len(cited))
            unsup = float(any(c is None for c in assign)) if it["missing_asks"] else float(not any(c is None for c in assign))
            vals.append(rec - 0.5 * wrong + 0.5 * unsup)
        obj = float(np.mean(vals))
        if best is None or obj > best["objective"]:
            best = dict(lo=lo, hi=hi, tau=tau, objective=obj)
    cal_path = ROOT / "configs" / "search_calibration.json"
    cal = json.loads(cal_path.read_text()) if cal_path.exists() else {}
    cal[search.name] = dict(best, tuned_on="dev split (30 requests), objective of eval/exp12.py --tune")
    cal_path.write_text(json.dumps(cal, indent=2) + "\n", encoding="utf-8")
    print("calibration", best)
    search.lo, search.hi, search.tau = best["lo"], best["hi"], best["tau"]
    search._cache.clear()

    # ---- 2. evaluation on the frozen test split
    test = items("test")
    retr = [dict(ndcg10=ndcg([h["clause_id"] for h in search.search(it["text"], k=10)], it["gold_clauses"]),
                 recall5=recall([h["clause_id"] for h in search.search(it["text"], k=10)], it["gold_clauses"])) for it in test]
    rows = []
    for it in test:
        form = {k: v for k, v in it["form"].items() if k != "agreement_type"}
        d = make_draft(it["agreement_type"], form, it["text"], search, mode="rules")
        res = dict(final=dict(fields=d["fields"], selections=d["selections"], issues=d["issues"], route=d["route"], reviewer_note=d["reviewer_note"]),
                   draft=None, trace=dict(n_calls=0, n_tool_calls=1, prompt_tokens=0, completion_tokens=0, latency_s=0))
        rows.append(dict(request_id=it["request_id"], **score(lib, it, res)))
    metrics = ["success", "success_core", "defect_recall", "false_alarm_on_clean", "route_correct", "field_accuracy", "ask_recall", "citation_accuracy",
               "hallucinated_clause_rate", "detect_unsupported_clause"]
    summary = {"config": dict(search=search.name, mode="rules", lo=search.lo, hi=search.hi, tau=search.tau)}
    lines = ["# Deployed configuration (free tier) on the frozen test split", "",
             f"Search `{search.name}` (Supabase Edge Function gte-small + Postgres full-text/pgvector RRF), drafting mode `rules` (no LLM), "
             f"calibration lo={search.lo}, hi={search.hi}, tau={search.tau} (dev split). 90 test requests; deterministic, so one run. "
             "Brackets: 95% bootstrap CIs over requests.", "", "| Metric | Deployed | ", "|---|---|"]
    for name, vals in (("retrieval nDCG@10 (whole request)", [r["ndcg10"] for r in retr]), ("retrieval Recall@5 (whole request)", [r["recall5"] for r in retr])):
        m, lo, hi = bootstrap_ci(vals)
        summary[name] = dict(mean=m, ci_low=lo, ci_high=hi)
        lines.append(f"| {name} | {m:.3f} [{lo:.3f}, {hi:.3f}] |")
    for m_ in metrics:
        vals = [r.get(m_, float("nan")) for r in rows]
        m, lo, hi = bootstrap_ci(vals)
        summary[m_] = dict(mean=m, ci_low=lo, ci_high=hi, n=int(np.sum(~np.isnan(np.asarray(vals, dtype=float)))))
        lines.append(f"| {m_} | {m:.3f} [{lo:.3f}, {hi:.3f}] |")
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, default=float) + "\n", encoding="utf-8")
    (OUT / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with open(OUT / "per_item.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, default=float) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
