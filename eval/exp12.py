"""Run Experiment 1 (skill files) and Experiment 2 (agent harness) on the frozen intake set.

  python eval/exp12.py --exp 1 [--conditions S0 S2] [--split test] [--seeds 1 2 3] [--n 0]
  python eval/exp12.py --exp 2 [--conditions H0 H3] ...
  python eval/exp12.py --tune          # tune tau for H3b / H-det on the dev split
  python eval/exp12.py --report 1|2    # rebuild summary, significance and figures from cached runs

Runs are cached in .cache/exp12-runs.jsonl, so an interrupted run resumes where it stopped.
Model: qwen2.5:7b via Ollama (S5 and S0s: qwen2.5:3b), temperature 0.3, seeds 1-3, plan section 5.1.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import math
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval.metrics.drafting_metrics import DEFECT_TYPES, ask_gold, score  # noqa: E402
from eval.metrics.retrieval_metrics import bootstrap_ci  # noqa: E402
from src.agreement.library import load_library  # noqa: E402
from src.common import CACHE, JsonCache, read_jsonl  # noqa: E402

EXP_CONDITIONS = {1: ["S0", "S1", "S2", "S3", "S4", "S5", "S0s"], 2: ["H-det", "H0", "H1", "H2", "H3", "H4", "H3b"]}
BASELINE = {1: "S0", 2: "H0"}
RUN_VERSION = "v1"
LOCK = threading.Lock()
TAU_PATH = ROOT / "eval" / "results" / "exp2" / "tau.json"


def load_items(split: str, n: int = 0) -> list[dict]:
    items = [r for r in read_jsonl(ROOT / "data" / "synthetic" / "intake.jsonl") if r["split"] == split]
    return items[:n] if n else items


def make_ctx(seed: int, search, llm, small, tau):
    from src.drafting.harness import Ctx
    return Ctx(lib=load_library(), search=search, llm=llm, seed=seed, small_llm=small, tau=tau)


def ensure_self_skill(llm) -> None:
    """S4: the model writes its own SKILL.md from the task description only (SkillsBench 'self-generated')."""
    path = ROOT / "skills" / "self-generated" / "SKILL.md"
    if path.exists():
        return
    from src.drafting.schema import OUTPUT_CONTRACT
    prompt = ("Write a SKILL.md file (Anthropic Agent Skills format: YAML front matter with `name` and `description`, then Markdown "
              "instructions) that teaches an AI assistant to do this task well:\n\n"
              "At a fund management company in Singapore regulated by the Monetary Authority of Singapore, staff submit a request form "
              "and a free-text message asking Legal for a standard agreement (NDA, investment management agreement, distribution agreement, "
              "side letter or subscription agreement). The assistant receives the form, the text and some candidate clauses from the firm's "
              "approved clause library, and must produce a structured draft for a human Legal reviewer in this format:\n\n"
              f"{OUTPUT_CONTRACT}\n\nWrite practical, specific instructions. Output only the SKILL.md content.")
    out = llm.generate(prompt, system="You are an expert at writing instructions for AI agents.", temperature=0.7, seed=0, max_tokens=1500)
    text = out["text"].strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    if not text.lstrip().startswith("---"):
        text = "---\nname: self-generated-legal-drafting\ndescription: Self-generated skill (Experiment 1, condition S4).\n---\n\n" + text
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")
    print(f"wrote {path} ({len(text.split())} words)")


def compact(res: dict) -> dict:
    d = res.get("draft")
    keep_draft = None if d is None else {k: d[k] for k in ("valid_json", "schema_ok", "agreement_type", "fields", "raw_fields", "selections", "issues", "route", "reviewer_note")}
    return dict(condition=res["condition"], request_id=res["request_id"], seed=res["seed"], final=res["final"], draft=keep_draft,
                trace={k: v for k, v in res["trace"].items()}, extra=res.get("extra", {}))


def run(exp: int, conds: list[str], split: str, seeds: list[int], n: int, workers: int) -> None:
    from src.llm.ollama import OllamaLLM
    from src.retrieval.service import ClauseSearch
    from src.drafting.harness import run_condition
    lib = load_library()
    items = load_items(split, n)
    runs = JsonCache("exp12-runs")
    search = ClauseSearch()
    llm = OllamaLLM("qwen2.5:7b", num_ctx=8192, cache_name="draft")
    small = OllamaLLM("qwen2.5:3b", num_ctx=8192, cache_name="draft")
    if "S4" in conds:
        ensure_self_skill(llm)
    tau = json.loads(TAU_PATH.read_text()) if TAU_PATH.exists() else {}
    if any(c in conds for c in ("H3b", "H-det")) and not tau:
        raise SystemExit("run --tune first")
    order = [c for c in conds if c not in ("S5", "S0s")] + [c for c in conds if c in ("S5", "S0s")]  # small model last: one model swap
    for cond in order:
        t0, done = time.time(), 0
        jobs = [(item, seed) for seed in seeds for item in items if runs.get(f"{RUN_VERSION}|{cond}|{item['request_id']}|{seed}") is None]
        print(f"[{time.strftime('%H:%M:%S')}] {cond}: {len(jobs)} runs to do ({len(items)} items x {len(seeds)} seeds)", flush=True)

        def one(job):
            item, seed = job
            ctx = make_ctx(seed, search, llm, small, tau)
            res = compact(run_condition(cond, item, ctx))
            res["metrics"] = score(lib, item, res)
            with LOCK:
                runs.put(f"{RUN_VERSION}|{cond}|{item['request_id']}|{seed}", res)
            return res

        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            for res in ex.map(one, jobs):
                done += 1
                if done % 15 == 0 or done == len(jobs):
                    el = time.time() - t0
                    print(f"  {cond} {done}/{len(jobs)}  {el / done:.1f}s/run  eta {el / done * (len(jobs) - done) / 60:.0f} min", flush=True)
        if cond in ("S5", "S0s"):
            small.unload()
    report(exp, conds, split, seeds)


# ------------------------------------------------------------------------------------------------------- tuning
def tune() -> None:
    """Tune the abstention cost tau of the A* assembler on the dev split (H3b with LLM requirements, H-det without)."""
    from src.llm.ollama import OllamaLLM
    from src.retrieval.service import ClauseSearch
    from src.drafting.assembly import astar_assign, rule_requirements
    from src.drafting.harness import Trace, extract_requirements
    lib = load_library()
    items = load_items("dev")
    search = ClauseSearch()
    llm = OllamaLLM("qwen2.5:7b", num_ctx=8192, cache_name="draft")
    grid = [round(x, 2) for x in np.arange(0.30, 1.01, 0.05)]
    out = {}
    for cond in ("H3b", "H-det"):
        prepared = []
        for item in items:
            for seed in (1, 2, 3) if cond == "H3b" else (1,):
                ctx = make_ctx(seed, search, llm, None, {})
                reqs = extract_requirements(ctx, item, Trace(ctx)) if cond == "H3b" else [dict(requirement=s, query=s) for s in rule_requirements(item["text"])]
                cands = [search.search(r["query"], k=5, agreement_type=item["agreement_type"]) for r in reqs]
                prepared.append((item, cands))
        rows = []
        for tau in grid:
            vals = []
            for item, cands in prepared:
                assign, _ = astar_assign(lib, cands, tau)
                cited = [c for c in assign if c]
                asks = item["asks"]
                rec = (sum(1 for a in asks if set(cited) & ask_gold(lib, item["agreement_type"], a)) / len(asks)) if asks else 1.0
                gold_any = {cid for cid, g in item["gold_clauses"].items() if g >= 2}
                wrong = sum(1 for c in cited if c not in gold_any) / max(1, len(cited))
                unsup_ok = float(any(c is None for c in assign)) if item["missing_asks"] else float(not any(c is None for c in assign))
                vals.append(rec - 0.5 * wrong + 0.5 * unsup_ok)
            rows.append(dict(tau=tau, objective=float(np.mean(vals))))
        best = max(rows, key=lambda r: r["objective"])
        out[cond] = best["tau"]
        out[f"{cond}_grid"] = rows
        print(cond, "best tau", best)
    TAU_PATH.parent.mkdir(parents=True, exist_ok=True)
    TAU_PATH.write_text(json.dumps(out, indent=2))


# ------------------------------------------------------------------------------------------------------- reporting
SUMMARY_METRICS = {
    1: ["success", "field_accuracy", "hallucinated_field_rate", "ask_recall", "citation_accuracy", "hallucinated_clause_rate", "defect_recall",
        "false_alarm_on_clean", "route_correct", "checklist_compliance", "format_valid", "total_tokens", "latency_s"],
    2: ["success", "success_core", "defect_recall", "false_alarm_on_clean", "route_correct", "field_accuracy", "hallucinated_field_rate",
        "ask_recall", "hallucinated_clause_rate", "n_calls", "n_tool_calls", "total_tokens", "latency_s"],
}
PCT = {"total_tokens", "latency_s", "n_calls", "n_tool_calls"}


def nanmean(xs):
    xs = [x for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x))]
    return float(np.mean(xs)) if xs else float("nan")


def collect(conds: list[str], split: str, seeds: list[int]) -> dict:
    runs = JsonCache("exp12-runs")
    items = load_items(split)
    data = {}
    for c in conds:
        per = {}
        for it in items:
            rs = [runs.get(f"{RUN_VERSION}|{c}|{it['request_id']}|{s}") for s in seeds]
            rs = [r for r in rs if r is not None]
            if rs:
                per[it["request_id"]] = rs
        if per:
            data[c] = per
    return data


def item_mean(rs: list[dict], m: str) -> float:
    return nanmean([r["metrics"].get(m) for r in rs])


def paired_diff(a: dict, b: dict, m: str, n_boot: int = 2000) -> tuple[float, float, float, int]:
    ids = [i for i in a if i in b]
    d = np.array([item_mean(a[i], m) - item_mean(b[i], m) for i in ids], dtype=float)
    d = d[~np.isnan(d)]
    if len(d) == 0:
        return float("nan"), float("nan"), float("nan"), 0
    rng = np.random.default_rng(0)
    boots = d[rng.integers(0, len(d), size=(n_boot, len(d)))].mean(axis=1)
    return float(d.mean()), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5)), len(d)


def mcnemar(a: dict, b: dict, m: str = "success") -> tuple[int, int, float]:
    """Exact McNemar on per-item majority-vote outcomes (>= 2 of 3 seeds)."""
    ids = [i for i in a if i in b]
    maj = lambda rs: item_mean(rs, m) >= 0.5  # noqa: E731
    b01 = sum(1 for i in ids if not maj(a[i]) and maj(b[i]))
    b10 = sum(1 for i in ids if maj(a[i]) and not maj(b[i]))
    p = binomtest(b10, b10 + b01, 0.5).pvalue if b10 + b01 else 1.0
    return b10, b01, float(p)


def report(exp: int, conds: list[str] | None, split: str, seeds: list[int]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    conds = conds or EXP_CONDITIONS[exp]
    data = collect(conds, split, seeds)
    out = ROOT / "eval" / "results" / f"exp{exp}"
    (out / "figures").mkdir(parents=True, exist_ok=True)
    items = {it["request_id"]: it for it in load_items(split)}
    summary = []
    lines = [f"# Experiment {exp}: {'skill files' if exp == 1 else 'agent harness'} (split: {split})", "",
             f"Means over requests (each request averaged over its seeds), 95% bootstrap CIs over requests in brackets. "
             f"Model qwen2.5:7b via Ollama (S5, S0s: qwen2.5:3b), temperature 0.3, seeds {seeds}.", ""]
    metrics = SUMMARY_METRICS[exp]
    lines += ["| Condition | n | " + " | ".join(metrics) + " |", "|---|---|" + "---|" * len(metrics)]
    for c, per in data.items():
        cells = []
        for m in metrics:
            vals = [item_mean(rs, m) for rs in per.values()]
            mean, lo, hi = bootstrap_ci(vals)
            summary.append(dict(condition=c, metric=m, mean=mean, ci_low=lo, ci_high=hi, n=len(per)))
            cells.append("–" if math.isnan(mean) else (f"{mean:.0f}" if m in PCT and m != "latency_s" and m != "n_calls" and m != "n_tool_calls" else
                                                      f"{mean:.1f}" if m in PCT else f"{mean:.3f} [{lo:.2f}, {hi:.2f}]"))
        lines.append(f"| {c} | {len(per)} | " + " | ".join(cells) + " |")
    # pass^k and per-defect detection
    lines += ["", "## Consistency and defect detection", "",
              "pass^k (tau-bench): share of requests where the run succeeds in all k seeds. Detection: share of planted defects of each type caught.", "",
              "| Condition | pass^1 | pass^3 | " + " | ".join(DEFECT_TYPES) + " | escalation precision | escalation recall | prompt injection resisted |",
              "|---|---|---|" + "---|" * len(DEFECT_TYPES) + "---|---|---|"]
    for c, per in data.items():
        full = [rs for rs in per.values() if len(rs) == len(seeds)]
        p1 = nanmean([r["metrics"]["success"] for rs in full for r in rs])
        pk = nanmean([float(all(r["metrics"]["success"] == 1.0 for r in rs)) for rs in full])
        det = []
        for t in DEFECT_TYPES:
            v = nanmean([r["metrics"].get(f"detect_{t}") for rs in per.values() for r in rs])
            det.append("–" if math.isnan(v) else f"{v:.2f}")
            summary.append(dict(condition=c, metric=f"detect_{t}", mean=v))
        tp = sum(r["metrics"]["esc_tp"] for rs in per.values() for r in rs)
        fp = sum(r["metrics"]["esc_fp"] for rs in per.values() for r in rs)
        fn = sum(r["metrics"]["esc_fn"] for rs in per.values() for r in rs)
        prec, rec = (tp / (tp + fp) if tp + fp else float("nan")), (tp / (tp + fn) if tp + fn else float("nan"))
        inj = nanmean([r["metrics"].get("injection_resisted") for rs in per.values() for r in rs])
        summary += [dict(condition=c, metric="pass^1", mean=p1), dict(condition=c, metric="pass^3", mean=pk),
                    dict(condition=c, metric="escalation_precision", mean=prec), dict(condition=c, metric="escalation_recall", mean=rec),
                    dict(condition=c, metric="injection_resisted", mean=inj)]
        lines.append(f"| {c} | {p1:.3f} | {pk:.3f} | " + " | ".join(det) + f" | {prec:.3f} | {rec:.3f} | {inj:.2f} |")
    # cost-adjusted
    lines += ["", "## Cost-adjusted performance", "", "Successes per 10,000 tokens (local model; tokens are the cost proxy, no API spend).", "",
              "| Condition | success | tokens per run | LLM calls per run | successes per 10k tokens | seconds per run |", "|---|---|---|---|---|---|"]
    for c, per in data.items():
        allr = [r for rs in per.values() for r in rs]
        s, tok = nanmean([r["metrics"]["success"] for r in allr]), nanmean([r["metrics"]["total_tokens"] for r in allr])
        calls, lat = nanmean([r["metrics"]["n_calls"] for r in allr]), nanmean([r["metrics"]["latency_s"] for r in allr])
        spt = s / tok * 1e4 if tok else float("inf")
        summary.append(dict(condition=c, metric="success_per_10k_tokens", mean=spt if tok else None))
        lines.append(f"| {c} | {s:.3f} | {tok:.0f} | {calls:.1f} | {'n/a (no LLM)' if not tok else f'{spt:.3f}'} | {lat:.1f} |")
    # significance vs baseline
    base = BASELINE[exp]
    if base in data:
        lines += ["", f"## Paired comparisons against {base}", "",
                  "Mean difference (condition minus baseline) over requests with a 95% paired bootstrap CI; exact McNemar test on per-request "
                  "majority success (b10 = requests only the condition solves, b01 = only the baseline).", "",
                  "| Condition | Δ success | Δ defect recall | Δ field accuracy | Δ ask recall | Δ route correct | McNemar b10/b01, p |", "|---|---|---|---|---|---|---|"]
        for c in data:
            if c == base:
                continue
            cells = []
            for m in ("success", "defect_recall", "field_accuracy", "ask_recall", "route_correct"):
                d, lo, hi, _ = paired_diff(data[c], data[base], m)
                sig = "*" if not math.isnan(d) and (lo > 0 or hi < 0) else ""
                cells.append(f"{d:+.3f} [{lo:+.2f}, {hi:+.2f}]{sig}")
                summary.append(dict(condition=c, metric=f"delta_{m}_vs_{base}", mean=d, ci_low=lo, ci_high=hi))
            b10, b01, p = mcnemar(data[c], data[base])
            lines.append(f"| {c} | " + " | ".join(cells) + f" | {b10}/{b01}, p={p:.3g} |")
        lines += ["", "\\* the 95% CI excludes zero."]
    if exp == 1:
        mods = defaultdict(int)
        n_s2 = 0
        for rs in data.get("S2", {}).values():
            for r in rs:
                n_s2 += 1
                for p in r["extra"].get("loaded_modules", []):
                    mods[p] += 1
        if n_s2:
            lines += ["", "## Which skill files did the model load (S2)?", ""] + [f"- `{p}`: {v / n_s2:.0%} of runs" for p, v in sorted(mods.items(), key=lambda x: -x[1])]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=float), encoding="utf-8")
    with open(out / "per_item.jsonl", "w", encoding="utf-8") as f:
        for c, per in data.items():
            for rid, rs in per.items():
                for r in rs:
                    f.write(json.dumps(dict(condition=c, request_id=rid, seed=r["seed"], route=r["final"]["route"], gold_route=items[rid]["gold_route"],
                                            issues=[i["type"] for i in r["final"]["issues"]], selections=r["final"]["selections"],
                                            metrics={k: v for k, v in r["metrics"].items()}), ensure_ascii=False, default=float) + "\n")
    # figures
    fig_metrics = ["success", "defect_recall", "field_accuracy", "ask_recall", "route_correct"] + (["checklist_compliance"] if exp == 1 else [])
    conds_ok = list(data)
    fig, ax = plt.subplots(figsize=(max(7, 1.2 * len(conds_ok) * len(fig_metrics) / 3), 4))
    w = 0.8 / len(fig_metrics)
    palette = ["#2a6f97", "#61a5c2", "#e07a5f", "#81b29a", "#f2cc8f", "#6d597a"]
    for k, m in enumerate(fig_metrics):
        means = [nanmean([item_mean(rs, m) for rs in data[c].values()]) for c in conds_ok]
        ax.bar(np.arange(len(conds_ok)) + k * w - 0.4 + w / 2, means, w, label=m.replace("_", " "), color=palette[k % len(palette)])
    ax.set_xticks(np.arange(len(conds_ok)))
    ax.set_xticklabels(conds_ok)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("mean over requests")
    ax.set_title(f"Experiment {exp}: {'skill files' if exp == 1 else 'agent harness'} ({split} split, {len(seeds)} seeds)")
    ax.legend(ncol=3, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.1), frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "figures" / "scoreboard.png", dpi=150)
    plt.close(fig)
    if exp == 2:
        fig, ax = plt.subplots(figsize=(6, 4))
        for c in conds_ok:
            allr = [r for rs in data[c].values() for r in rs]
            ax.scatter(nanmean([r["metrics"]["total_tokens"] for r in allr]), nanmean([r["metrics"]["success"] for r in allr]), s=60, color="#2a6f97")
            ax.annotate(c, (nanmean([r["metrics"]["total_tokens"] for r in allr]), nanmean([r["metrics"]["success"] for r in allr])),
                        textcoords="offset points", xytext=(5, 5), fontsize=9)
        ax.set_xlabel("tokens per request (prompt + completion)")
        ax.set_ylabel("task success")
        ax.set_title("Cost vs quality (Experiment 2)")
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        fig.savefig(out / "figures" / "cost_vs_quality.png", dpi=150)
        plt.close(fig)
    print("\n".join(lines))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", type=int, choices=[1, 2])
    ap.add_argument("--conditions", nargs="*")
    ap.add_argument("--split", default="test")
    ap.add_argument("--seeds", type=int, nargs="*", default=[1, 2, 3])
    ap.add_argument("--n", type=int, default=0)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--tune", action="store_true")
    ap.add_argument("--report", type=int, choices=[1, 2])
    a = ap.parse_args()
    if a.tune:
        tune()
    elif a.report:
        report(a.report, a.conditions, a.split, a.seeds)
    else:
        run(a.exp, a.conditions or EXP_CONDITIONS[a.exp], a.split, a.seeds, a.n, a.workers)


if __name__ == "__main__":
    main()
