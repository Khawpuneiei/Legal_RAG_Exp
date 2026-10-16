"""Post-hoc, exploratory (designed after seeing the Experiment 2 test results, so not a pre-registered condition):
rules-only drafting (H-det) plus only the LLM's semantic signal, i.e. the unsupported_clause flags from an LLM run.

No new model calls: it recombines cached runs. For each request and seed, the final issues are H-det's issues plus
the unsupported_clause issues (explicit, or implied by a null selection) from the LLM condition's own output; the
route is recomputed with the routing policy. Writes eval/results/exp2/posthoc_hybrid.md.

    python eval/posthoc_hybrid.py
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval.metrics.drafting_metrics import score  # noqa: E402
from eval.metrics.retrieval_metrics import bootstrap_ci  # noqa: E402
from src.agreement.library import load_library  # noqa: E402
from src.agreement.validation import check_selections, merge_issues, route  # noqa: E402
from src.common import JsonCache, read_jsonl  # noqa: E402

METRICS = ["success", "defect_recall", "false_alarm_on_clean", "route_correct", "ask_recall", "detect_unsupported_clause"]


def llm_unsupported(run: dict) -> list[dict]:
    d = run.get("draft") or {}
    flags = [i for i in d.get("issues", []) if i.get("type") == "unsupported_clause"]
    flags += [dict(type="unsupported_clause", field=None, detail=s.get("requirement", ""), source="llm-null-selection")
              for s in d.get("selections", []) if not s.get("clause_id")]
    return flags


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    lib = load_library()
    runs = JsonCache("exp12-runs")
    items = [r for r in read_jsonl(ROOT / "data" / "synthetic" / "intake.jsonl") if r["split"] == "test"]
    rows = {}
    for donor in ("H0", "H1", "H3b"):
        per_item = []
        for it in items:
            vals = []
            for seed in (1, 2, 3):
                base, llm = runs.get(f"v1|H-det|{it['request_id']}|{seed}"), runs.get(f"v1|{donor}|{it['request_id']}|{seed}")
                if not base or not llm:
                    continue
                res = copy.deepcopy(base)
                fin = res["final"]
                extra = llm_unsupported(llm) if donor != "H3b" else [i for i in llm["final"]["issues"] if i["type"] == "unsupported_clause"]
                fin["issues"] = merge_issues(fin["issues"], extra[:1])  # one flag is enough to escalate
                _, sel = check_selections(lib, it["agreement_type"], [s["clause_id"] for s in fin["selections"] if s["clause_id"]])
                fin["route"] = route(lib, fin["issues"], bool(sel["material"]))
                vals.append(score(lib, it, res))
            per_item.append(vals)
        rows[f"H-det + {donor} unsupported flags"] = per_item
    base_items = [[runs.get(f"v1|H-det|{it['request_id']}|{s}")["metrics"] for s in (1, 2, 3)] for it in items]
    rows = {"H-det (reference)": base_items, **rows}
    lines = ["# Post-hoc hybrid: rules plus the LLM's semantic flags (exploratory)", "",
             "Designed after the Experiment 2 test results were seen, so treat it as a hypothesis for the next frozen test set, not a result. "
             "No new model calls: H-det's output on each request and seed, plus the first `unsupported_clause` flag from the named LLM run, "
             "route recomputed by the policy. Means over the 90 test requests (seeds averaged), 95% bootstrap CIs.", "",
             "| Variant | " + " | ".join(METRICS) + " |", "|---|" + "---|" * len(METRICS)]
    out = {}
    for name, per_item in rows.items():
        cells = []
        for m in METRICS:
            vals = []
            for v in per_item:
                xs = [x.get(m) for x in v if x.get(m) is not None and x.get(m) == x.get(m)]
                if xs:
                    vals.append(sum(xs) / len(xs))
            mean, lo, hi = bootstrap_ci(vals)
            out.setdefault(name, {})[m] = mean
            cells.append("–" if mean != mean else f"{mean:.3f} [{lo:.2f}, {hi:.2f}]")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    (ROOT / "eval" / "results" / "exp2" / "posthoc_hybrid.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ROOT / "eval" / "results" / "exp2" / "posthoc_hybrid.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
