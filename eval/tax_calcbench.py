"""TaxCalcBench (Column Tax, MIT licence) TY 2024 on Claude Opus 5.5: a public tax benchmark with a published leaderboard.

Its 51 TY24 federal cases give the taxpayer's data as JSON; the model returns a completed Form 1040, which the benchmark's
own evaluator scores against the expected IRS MeF XML on 19 lines (strict: every line exact; lenient: within $5; by line:
share of lines right). The prompt template, test data and evaluator are imported unchanged from a local clone
(TAXCALCBENCH_DIR, default ../benchmarks/tax-calc-bench; github.com/column-tax/tax-calc-bench). The published TY24
leaderboard has no Claude Opus 5.5 row. Its TY24 path sends the thinking level as the reasoning effort, so its default
level ("high") is effort "high" (`--effort high`); "xhigh" is one level up (its TY25 mapping of "high" for adaptive-thinking
Claude models). One run per case; the leaderboard's newer rows are single runs too, its older ones means of 4, each at the
model's best thinking level per column. No server-side fallback,
so every return is Opus 5.5's own. Replies are cached by model, effort and case: the prompt and data
come from the clone, so a changed clone needs a fresh cache.

    python eval/tax_calcbench.py run [--effort high] [--workers 4] [--limit N]   # replies cached in .cache/taxcalcbench/
    python eval/tax_calcbench.py summary [--effort high]   # -> eval/results/taxcalcbench/per_case_<effort>.jsonl, summary_<effort>.md
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.tax_experiment import load_keys  # noqa: E402
from src.common import CACHE, ROOT  # noqa: E402
from src.llm.claude import PRICES  # noqa: E402

BENCH = Path(os.environ.get("TAXCALCBENCH_DIR", ROOT.parent / "benchmarks" / "tax-calc-bench"))
sys.path.insert(0, str(BENCH))
from tax_calc_bench.config import TAX_YEAR  # noqa: E402
from tax_calc_bench.tax_return_evaluator import TaxReturnEvaluator  # noqa: E402
from tax_calc_bench.ty24_prompt import TAX_RETURN_GENERATION_PROMPT  # noqa: E402

MODEL = "claude-opus-5-5"
CASES = BENCH / "tax_calc_bench" / "ty24" / "test_data"
REPLIES = CACHE / "taxcalcbench" / MODEL
OUT = ROOT / "eval" / "results" / "taxcalcbench"
# The published TY24 leaderboard (README of the clone, read 7 November 2026): strict, lenient, by line, by line lenient.
# Each column is the model's best thinking level; GPT-5.4 Pro, GPT-5.4, Opus 4.6, Gemini 3.1 Pro and Sonnet 4.6 are single runs,
# Gemini 3 Pro, Opus 4.5 and GPT-5 means of 4.
PUBLISHED = [("GPT-5.4 Pro", 62.75, 72.55, 89.99, 93.40), ("GPT-5.4", 62.75, 66.67, 89.78, 91.12),
             ("Claude Opus 4.6", 52.94, 64.71, 87.00, 89.16), ("Gemini 3.1 Pro", 49.02, 68.63, 88.54, 92.16),
             ("Claude Sonnet 4.6", 37.25, 56.86, 84.21, 88.65), ("Gemini 3 Pro", 36.27, 73.53, 85.42, 93.83),
             ("Claude Opus 4.5", 36.27, 58.33, 82.51, 87.38), ("GPT-5", 31.86, 54.41, 81.45, 86.09)]
# The best published value in each column (strict, lenient, by line, by line lenient) and its model
BEST = [(62.75, "GPT-5.4 Pro, GPT-5.4"), (73.53, "Gemini 3 Pro"), (89.99, "GPT-5.4 Pro"), (93.83, "Gemini 3 Pro")]


def cases() -> list[str]:
    return sorted(p.name for p in CASES.iterdir() if (p / "input.json").exists())


def prompt(case: str) -> str:
    data = json.loads((CASES / case / "input.json").read_text(encoding="utf-8"))
    return TAX_RETURN_GENERATION_PROMPT.format(tax_year=TAX_YEAR, tool_use_hint="", input_data=json.dumps(data))


def generate(client, case: str, effort: str) -> dict:
    path = REPLIES / effort / f"{case}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    t0 = time.monotonic()
    with client.messages.stream(model=MODEL, max_tokens=128000, output_config={"effort": effort},
                                messages=[{"role": "user", "content": prompt(case)}]) as stream:
        msg = stream.get_final_message()
    u = msg.usage
    out = dict(case=case, effort=effort, model=msg.model, stop_reason=msg.stop_reason, seconds=round(time.monotonic() - t0, 1),
               text="".join(b.text for b in msg.content if b.type == "text"),
               input_tokens=u.input_tokens, output_tokens=u.output_tokens)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def run(effort: str, workers: int, limit: int | None) -> None:
    import anthropic
    load_keys()
    client = anthropic.Anthropic(max_retries=5, timeout=3600)
    todo = cases()[:limit]
    with cf.ThreadPoolExecutor(workers) as ex:
        futures = {ex.submit(generate, client, c, effort): c for c in todo}
        for f in cf.as_completed(futures):
            try:
                r = f.result()
                print(f"  {r['case']}: {r['stop_reason']}, {r['output_tokens']} output tokens, {r['seconds']}s", flush=True)
            except anthropic.APIError as error:   # keep the others going; a rerun retries this case
                print(f"  {futures[f]}: {type(error).__name__}: {error}", flush=True)
    summary(effort)


def summary(effort: str) -> None:
    evaluator, rows = TaxReturnEvaluator(), []
    for case in cases():
        path = REPLIES / effort / f"{case}.json"
        if not path.exists():
            continue
        r = json.loads(path.read_text(encoding="utf-8"))
        ev = evaluator.evaluate(r["text"], (CASES / case / "output.xml").read_text(encoding="utf-8"))
        inp, outp = PRICES[r["model"]][:2]
        rows.append(dict(case=case, stop_reason=r["stop_reason"], strict=ev.strictly_correct_return, lenient=ev.lenient_correct_return,
                         by_line=ev.correct_by_line_score, by_line_lenient=ev.lenient_correct_by_line_score,
                         wrong_lines=[ln.split(":")[0] for ln in ev.report.splitlines() if "✗" in ln],
                         seconds=r["seconds"], output_tokens=r["output_tokens"],
                         cost=(r["input_tokens"] * inp + r["output_tokens"] * outp) / 1e6))
    if not rows:
        raise SystemExit("no replies yet")
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / f"per_case_{effort}.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r) + "\n" for r in rows)
    n = len(rows)

    def pct(key: str) -> float:
        return 100 * sum(r[key] for r in rows) / n

    lines = [f"# TaxCalcBench TY 2024: Claude Opus 5.5 (effort {effort}), {n} of {len(cases())} cases", "",
             "One run per case, the benchmark's own prompt, data and evaluator. The published rows are the leaderboard's "
             "(each column at the model's best thinking level; GPT-5.4 Pro, GPT-5.4, Opus 4.6, Gemini 3.1 Pro and Sonnet 4.6 single "
             "runs, Gemini 3 Pro, Opus 4.5 and GPT-5 means of 4).", "",
             "| Model | Correct returns (strict) | Correct returns (lenient) | Correct (by line) | Correct (by line, lenient) |",
             "|---|---|---|---|---|",
             f"| **Claude Opus 5.5 ({effort}), this run** | **{pct('strict'):.2f}%** | **{pct('lenient'):.2f}%** | "
             f"**{pct('by_line'):.2f}%** | **{pct('by_line_lenient'):.2f}%** |"]
    lines += [f"| {m} (published) | {s:.2f}% | {le:.2f}% | {bl:.2f}% | {bll:.2f}% |" for m, s, le, bl, bll in PUBLISHED]
    lines += ["", "Best published value per column: " + "; ".join(f"{v:.2f}% ({m})" for v, m in BEST) + ". The published "
              "rows are a selection of the 19 on the leaderboard."]
    wrong: dict[str, int] = {}
    for r in rows:
        for ln in r["wrong_lines"]:
            wrong[ln] = wrong.get(ln, 0) + 1
    lines += ["", f"Cost {sum(r['cost'] for r in rows):.2f} USD at list prices ({sum(r['cost'] for r in rows) / n:.2f} per return); "
              f"{sum(r['seconds'] for r in rows) / n:.0f} s per return; stop reasons "
              f"{dict((s, sum(r['stop_reason'] == s for r in rows)) for s in {r['stop_reason'] for r in rows})}.", "",
              "Lines most often wrong: " + ", ".join(f"{k} ({v})" for k, v in sorted(wrong.items(), key=lambda kv: -kv[1])[:8]) + "."]
    (OUT / f"summary_{effort}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("stage", choices=["run", "summary"])
    ap.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"],
                    help="high: the benchmark's TY24 default level, sent as the effort")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=None, help="only the first N cases (alphabetical)")
    args = ap.parse_args()
    if args.stage == "run":
        run(args.effort, args.workers, args.limit)
    else:
        summary(args.effort)


if __name__ == "__main__":
    main()
