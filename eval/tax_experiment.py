"""TaxRAG: do the Experiment 3 retrieval methods transfer from legal agreements to Singapore income tax?

Runs the teammate's retrieval configs (github.com/Saiharshaa/SGtax-rag) and the Experiment 3 methods
(reranker, contextual chunks, A* graph expansion, calibrated abstention) on his corpus and scoring, on two
question sets: his 28 questions ("reference") and our held-out set (dev split for every tuning choice, test
split frozen). See docs/taxrag-results.md.

    python eval/tax_experiment.py rank        # flat conditions -> per_query.jsonl, rankings.jsonl
    python eval/tax_experiment.py graph       # R6 graph expansion at the 2,500-token budget
    python eval/tax_experiment.py gate        # calibrated abstention
    python eval/tax_experiment.py report      # summary.md, significance.md, figures
    python eval/tax_experiment.py all
Needs the teammate's repo in TAX_RAG_DIR (default ../bc3415-tax-rag) and, for R5, the chunk contexts
(python -m src.tax.contextual).
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common import ROOT, read_jsonl  # noqa: E402
from src.retrieval.rerank import Reranker  # noqa: E402
from src.tax.contextual import OUT as CONTEXTS  # noqa: E402
from src.tax.corpus import QUESTION_SETS, TAX_RAG_DIR, chunks, load_tax_questions, spans, tax_commit, tax_rag  # noqa: E402
from src.tax.graph import TaxGraph  # noqa: E402
from src.tax.pipeline import CONDITIONS, FETCH, FIRST_STAGE_K, NEEDS_KEY, RERANKERS, IntegrationReranker, TaxSearch, rerank  # noqa: E402

OUT = ROOT / "eval" / "results" / "tax"
K, MRR_DEPTH = 5, 10
GRAPH_GRID = dict(lam=[0.0, 0.2, 0.5, 1.0, 2.0], mu=[0.0, 0.5, 1.0, 2.0], seeds=[3, 5, 8])


def question_sets() -> list:
    qs = [q for q in load_tax_questions("reference")]
    if QUESTION_SETS["heldout"].exists():
        qs += load_tax_questions("heldout")
    for q in qs:
        q.qset = "reference" if q.split == "reference" else "heldout"
    return qs


def load_contexts() -> dict[str, str]:
    have = {r["chunk_id"]: r["context"] for r in read_jsonl(CONTEXTS)} if CONTEXTS.exists() else {}
    missing = [c.chunk_id for c in chunks("structured") if c.chunk_id not in have]
    if missing:
        raise SystemExit(f"{len(missing)} chunks have no context yet: run python -m src.tax.contextual")
    return have


def unit_ndcg(ranked: list, gold: set, sp: dict, k: int = 10) -> float:
    """nDCG@k over gold units: a rank gains 1 when its chunk hits a gold unit not hit higher up."""
    rag = tax_rag()
    seen, dcg = set(), 0.0
    for i, chunk in enumerate(ranked[:k], start=1):
        new = rag.evaluate.units_hit(chunk, gold, sp) - seen
        if new:
            dcg += 1.0 / math.log2(i + 1)
            seen |= new
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(gold), k) + 1))
    return dcg / ideal if ideal else 0.0


def score(ranked: list, q, sp: dict, budget: int) -> dict:
    rag = tax_rag()
    gold = q.gold_units
    return dict(recall5=rag.evaluate.recall_at_k(ranked, gold, sp, K),
                rr10=rag.evaluate.reciprocal_rank(ranked[:MRR_DEPTH], gold, sp),
                budget_recall=rag.evaluate.recall_at_k(rag.retrieve.within_budget(ranked, budget), gold, sp, k=len(ranked)),
                ndcg10=unit_ndcg(ranked, gold, sp))


def base_row(q, condition: str) -> dict:
    return dict(qset=q.qset, split=q.split, qid=q.id, type=q.type, answerable=q.answerable, condition=condition)


class Runner:
    def __init__(self):
        self.rag = tax_rag()
        self.budget = self.rag.generate.CONTEXT_TOKENS
        self.questions = question_sets()
        self.sp = spans()
        self.embedders: dict = {}
        self.searches: dict = {}
        self.rerankers: dict = {}
        self._contexts = None

    def search(self, embedder: str, contextual: bool) -> TaxSearch:
        key = (embedder, contextual)
        if key not in self.searches:
            if contextual and self._contexts is None:
                self._contexts = load_contexts()
            s = TaxSearch(embedder, self._contexts if contextual else None, self.embedders)
            s.prepare([q.question for q in self.questions])
            self.searches[key] = s
        return self.searches[key]

    def reranker(self, key: str, max_length: int = 512):
        if (key, max_length) not in self.rerankers:
            self.rerankers[(key, max_length)] = (IntegrationReranker(max_length) if key == "minilm-onnx-int8"
                                                 else Reranker(RERANKERS[key], max_length=max_length))
        return self.rerankers[(key, max_length)]

    def ranked(self, condition: str, q) -> tuple[list, float | None]:
        spec = CONDITIONS[condition]
        s = self.search(spec.get("embedder", "bge-m3"), bool(spec.get("contextual")))
        if not spec.get("rerank"):
            cfg = self.rag.retrieve.CONFIGS[spec["first"]]
            top = None
            if cfg.dense:   # no reranker: the best cosine similarity is the confidence the gate can use
                top = s.retriever.corpus(cfg.corpus).dense.search(s.query_embedder.embed_query(q.question), 1)[0][1]
            return s.first_stage(q.question, spec["first"], FETCH), top
        cands = s.first_stage(q.question, spec["first"], FIRST_STAGE_K)
        if not cands:
            return [], None
        order, scores = rerank(self.reranker(spec["rerank"], spec.get("max_length", 512)), s, q.question, cands,
                               spec.get("fuse", False), spec.get("rerank_top"))
        return order, max(scores)

    # ------------------------------------------------------------------ stages
    def rank(self, names: list[str]) -> None:
        rows, rank_rows = [], []
        for name in names:
            t0 = time.time()
            if name in NEEDS_KEY:
                try:
                    self.search("gemini", False)
                except self.rag.embed.MissingApiKey as e:
                    print(f"  {name:32s} pending: {e}")
                    continue
            for q in self.questions:
                ranked, top = self.ranked(name, q)
                row = base_row(q, name)
                if q.answerable:
                    row.update(score(ranked, q, self.sp, self.budget))
                row["top_score"] = top
                rows.append(row)
                rank_rows.append(dict(qset=q.qset, qid=q.id, condition=name, chunk_ids=[c.chunk_id for c in ranked[:FETCH]]))
            ans = [r for r in rows if r["condition"] == name and r["answerable"]]
            print(f"  {name:32s} budget recall {np.mean([r['budget_recall'] for r in ans]):.3f}  "
                  f"MRR@10 {np.mean([r['rr10'] for r in ans]):.3f}  ({time.time() - t0:.0f}s)", flush=True)
        replace_rows(OUT / "per_query.jsonl", rows, {(r["condition"]) for r in rows})
        replace_rows(OUT / "rankings.jsonl", rank_rows, {(r["condition"]) for r in rank_rows})

    def graph(self, seed: str = "R5") -> None:
        """R6 at the same budget, seeded by a flat ranking: R5 (local models), or the teammate's `improved` on his Gemini
        index (structured_routed@gemini). Grid search on held-out dev; every other split is untouched."""
        spec = CONDITIONS[seed]
        s = self.search(spec.get("embedder", "bge-m3"), bool(spec.get("contextual")))
        g = TaxGraph(chunks("structured"), s.doc_vectors, self.rag.chunk.count_tokens)
        corpus = s.retriever.corpus("structured")
        answerable = [q for q in self.questions if q.answerable]
        flat = {q.id + q.qset: self.ranked(seed, q)[0] for q in answerable}
        # the flat budgeted hits: their dependencies are the fixed denominator of hit_dependencies_complete
        hits_of = {k: [c.chunk_id for c in self.rag.retrieve.within_budget(r, self.budget)] for k, r in flat.items()}
        suffix = "" if seed == "R5" else "@" + seed.split("@")[-1]

        def evidence(strategy: str, q, lam=None, mu=None, n_seeds=5) -> tuple[list[str], int]:
            ranked = flat[q.id + q.qset]
            ids = [c.chunk_id for c in ranked]
            if strategy == "flat":
                ev = [c.chunk_id for c in self.rag.retrieve.within_budget(ranked, self.budget)]
                return ev, 0
            if strategy == "onehop":   # the teammate's expansion, but counted inside the budget
                hits = self.rag.retrieve.within_budget(ranked, self.budget)
                extra = corpus.expand(hits)
                room = self.budget - sum(self.rag.chunk.count_tokens(c.text) for c in extra)
                base = [c.chunk_id for c in self.rag.retrieve.within_budget(ranked, room)] if room > 0 else []
                return base + [c.chunk_id for c in extra if c.chunk_id not in base], 0
            if strategy in ("deployed", "expand", "expand_dep"):   # the budgeted hits, then extra chunks (his app's layout)
                hits = hits_of[q.id + q.qset]
                if strategy == "deployed":   # his one-hop expansion: up to 3 cited sections, beyond the budget
                    return hits + [c.chunk_id for c in corpus.expand([g.chunks[c] for c in hits])], 0
                return hits + g.expand(hits, s.query_embedder.embed_query(q.question), allowance, lam, mu,
                                       follow_seed_only=strategy == "expand"), 0
            seeds = ids[:n_seeds]
            if strategy == "bfs":
                out = g.graph.bfs(seeds, self.budget)
            else:
                out = g.graph.astar(seeds, s.query_embedder.embed_query(q.question), self.budget, lam=lam, mu=mu)
            return g.fill(out["evidence"], ids, self.budget), out["expanded"]

        def measure(ev: list[str], q) -> dict:
            hit = set().union(*(self.rag.evaluate.units_hit(g.chunks[c], q.gold_units, self.sp) for c in ev)) if ev else set()
            m = dict(budget_recall=len(hit) / len(q.gold_units), evidence_tokens=sum(self.rag.chunk.count_tokens(g.chunks[c].text) for c in ev),
                     evidence_chunks=len(ev))
            m.update(g.completeness(ev, hits_of[q.id + q.qset]))
            return m

        def objective(ms: list[dict]) -> float:
            return float(np.mean([(m["budget_recall"] + m["refers_to_complete"] + m["defined_in_complete"]) / 3 for m in ms]))

        dev = [q for q in answerable if q.split == "dev"]
        grid, expand_grid, dep_grid = [], [], []
        allowance = 0
        if dev:
            for lam, mu, n in itertools.product(GRAPH_GRID["lam"], GRAPH_GRID["mu"], GRAPH_GRID["seeds"]):
                grid.append(dict(lam=lam, mu=mu, seeds=n, objective=objective([measure(evidence("astar", q, lam, mu, n)[0], q) for q in dev])))
            best = max(grid, key=lambda r: (r["objective"], -r["lam"], -r["mu"]))
            # R6x gets the extra tokens his expansion adds on dev, on average (rounded to 50), in place of his 3 sections
            extra = [measure(evidence("deployed", q)[0], q)["evidence_tokens"] - measure(evidence("flat", q)[0], q)["evidence_tokens"] for q in dev]
            allowance = int(round(float(np.mean(extra)) / 50) * 50)
            for lam, mu in itertools.product(GRAPH_GRID["lam"], GRAPH_GRID["mu"]):
                expand_grid.append(dict(lam=lam, mu=mu, objective=objective([measure(evidence("expand", q, lam, mu)[0], q) for q in dev])))
            best_x = max(expand_grid, key=lambda r: (r["objective"], -r["lam"], -r["mu"]))
            # R6y, added after R6x's dependency score turned out to grow with what the expansion itself brings in:
            # dependency edges only, tuned on dev for gold recall and the hits' own dependencies (a fixed denominator)
            for lam, mu in itertools.product(GRAPH_GRID["lam"], GRAPH_GRID["mu"]):
                ms = [measure(evidence("expand_dep", q, lam, mu)[0], q) for q in dev]
                dep_grid.append(dict(lam=lam, mu=mu, objective=float(np.mean([(m["budget_recall"] + m["hit_dependencies_complete"]) / 2
                                                                               for m in ms]))))
            best_y = max(dep_grid, key=lambda r: (r["objective"], -r["lam"], -r["mu"]))
        else:
            best = dict(lam=0.2, mu=1.0, seeds=5, objective=None)
            best_x = best_y = dict(lam=0.2, mu=1.0, objective=None)
        path = OUT / "graph_tuning.json"   # {seed condition: {grid, best, expand: {allowance, grid, best}}}
        tuning = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        tuning = {} if "grid" in tuning else tuning
        tuning[seed] = dict(grid=grid, best=best, expand=dict(allowance=allowance, grid=expand_grid, best=best_x),
                            expand_dep=dict(allowance=allowance, grid=dep_grid, best=best_y))
        path.write_text(json.dumps(tuning, indent=1) + "\n", encoding="utf-8")
        print(f"  R6d{suffix} (seeded by {seed}) tuned on held-out dev: {best}")
        print(f"  R6x{suffix} (his hits + A* dependencies in place of his expansion, {allowance} extra tokens) tuned on dev: {best_x}")
        print(f"  R6y{suffix} (the same, dependency edges only) tuned on dev: {best_y}")
        flat_name = "R5@budget" if seed == "R5" else f"{seed}@budget"
        plan = {flat_name: ("flat", None, None, 5), f"R6-onehop{suffix}": ("onehop", None, None, 5), f"R6a{suffix}": ("bfs", None, None, 5),
                f"R6c{suffix}": ("astar", 0.2, 1.0, 5), f"R6d{suffix}": ("astar", best["lam"], best["mu"], best["seeds"]),
                f"{seed}+expand": ("deployed", None, None, 5), f"R6x{suffix}": ("expand", best_x["lam"], best_x["mu"], 5),
                f"R6y{suffix}": ("expand_dep", best_y["lam"], best_y["mu"], 5)}
        rows = []
        for name, (strategy, lam, mu, n) in plan.items():
            t0 = time.time()
            for q in answerable:
                ev, expanded = evidence(strategy, q, lam, mu, n)
                rows.append(dict(base_row(q, name), nodes_expanded=expanded, **measure(ev, q)))
            sub = [r for r in rows if r["condition"] == name]
            print(f"  {name:10s} budget recall {np.mean([r['budget_recall'] for r in sub]):.3f}  dependencies complete "
                  f"{np.mean([r['dependencies_complete'] for r in sub]):.3f}  ({time.time() - t0:.0f}s)", flush=True)
        replace_rows(OUT / "graph_per_query.jsonl", rows, set(plan))

    def gate(self) -> None:
        """Calibrated abstention: refuse before any LLM call when the best reranker score (or, without a reranker, the
        best dense similarity) is below tau."""
        rows = read_jsonl(OUT / "per_query.jsonl")
        out = {}
        for cond in CONDITIONS:
            sub = [r for r in rows if r["condition"] == cond and r.get("top_score") is not None]
            dev = [r for r in sub if r["split"] == "dev"]
            if not dev:
                continue
            cands = sorted({r["top_score"] for r in dev})
            # scores are logits or probabilities depending on the model: candidate thresholds span what dev saw
            taus = [cands[0] - 1.0] + [(a + b) / 2 for a, b in zip(cands, cands[1:])] + [cands[-1] + 1.0]

            def rates(rs, tau):
                oos = [r for r in rs if not r["answerable"]]
                ans = [r for r in rs if r["answerable"]]
                return (np.mean([r["top_score"] < tau for r in oos]) if oos else float("nan"),
                        np.mean([r["top_score"] < tau for r in ans]) if ans else float("nan"))

            # Youden's J on dev: OOS refused minus answerable refused; ties go to the lower tau (fewer refusals)
            tau = max(taus, key=lambda t: (rates(dev, t)[0] - rates(dev, t)[1], -t))
            res = {"tau": tau}
            for split in ("dev", "test", "reference"):
                rs = [r for r in sub if r["split"] == split]
                oos_ref, ans_ref = rates(rs, tau)
                res[split] = dict(oos_refused=oos_ref, answerable_refused=ans_ref, n_oos=sum(not r["answerable"] for r in rs),
                                  n_answerable=sum(r["answerable"] for r in rs))
            out[cond] = res
            print(f"  {cond:8s} tau={tau:.4f}  test: OOS refused {res['test']['oos_refused']:.2f}, "
                  f"answerable refused {res['test']['answerable_refused']:.2f}; reference: OOS {res['reference']['oos_refused']:.2f}, "
                  f"answerable {res['reference']['answerable_refused']:.2f}")
        (OUT / "gate.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")


def replace_rows(path: Path, new: list[dict], conditions: set[str]) -> None:
    """Rewrite `path` with the rows of other conditions kept and these conditions' rows replaced."""
    old = [r for r in read_jsonl(path) if r["condition"] not in conditions] if path.exists() else []
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in old + new:
            f.write(json.dumps(r) + "\n")


def provenance() -> dict:
    h = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest() if Path(p).exists() else None  # noqa: E731
    return dict(teammate_commit=tax_commit(), reference_sha256=h(QUESTION_SETS["reference"]), heldout_sha256=h(QUESTION_SETS["heldout"]),
                contexts_sha256=h(CONTEXTS), rerankers=RERANKERS)


def load_keys() -> None:
    for env in (ROOT / ".env", TAX_RAG_DIR / ".env"):   # GEMINI_API_KEY for the @gemini rows (both files are git-ignored)
        load_dotenv(env)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("stage", choices=["rank", "graph", "gate", "report", "all"])
    ap.add_argument("--conditions", nargs="*", default=None)
    args = ap.parse_args()
    load_keys()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.stage in ("rank", "graph", "gate", "all"):
        runner = Runner()
        print(f"{len(runner.questions)} questions ({sum(q.answerable for q in runner.questions)} answerable)")
    if args.stage in ("rank", "all"):
        runner.rank(args.conditions or list(CONDITIONS))
    if args.stage in ("graph", "all"):
        runner.graph("R5")
        try:
            runner.search("gemini", False)
            runner.graph("structured_routed@gemini")
        except runner.rag.embed.MissingApiKey as e:
            print(f"  graph on the Gemini ranking pending: {e}")
    if args.stage in ("gate", "all"):
        runner.gate()
    if args.stage in ("report", "all"):
        from eval.tax_report import report
        report(OUT, provenance())


if __name__ == "__main__":
    main()
