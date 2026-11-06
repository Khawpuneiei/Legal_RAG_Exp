"""Clause-graph expansion of retrieved seeds (plan R6; README section 2.4.2).

Nodes are clause ids. Edges come from data/synthetic/edges.jsonl (DEFINED_IN, REFERS_TO, REQUIRES,
ALTERNATIVE_OF) plus RELATED_TO edges between each clause and its 3 nearest neighbours by embedding.
Given seeds from the best flat retriever (R5) and a token budget, each strategy returns an ordered
evidence set:

* R6a  bfs    - breadth-first to depth 2 over DEFINED_IN and REFERS_TO.
* R6b  ppr    - Personalized PageRank from the seeds, nodes taken in PageRank order.
* R6c  astar  - best-first search with f = g + h, admissible h (lambda <= c_min, mu = 1).
* R6d  astar  - the same search with lambda and mu tuned on the dev split (h may be inadmissible).

g(n) = sum of edge costs on the path + token_cost(n) / budget
h(n) = lambda * (1 - cos(n, q)) + mu * unresolved(n) * c_min

The same search runs on the tax corpus (src/tax/graph.py), where a dependency can be satisfied by any of
several nodes (a cross-reference to "section 37B" is resolved by any chunk of s 37B): an edge may carry a
"group" key, and a dependency counts as resolved when any node of its group is in the evidence. Edges
without a group are their own group, so the clause library behaves exactly as before.
"""
from __future__ import annotations

import heapq
import time
from collections import defaultdict, deque

import networkx as nx
import numpy as np

EDGE_COST = {"CONTAINS": 0.1, "DEFINED_IN": 0.2, "REFERS_TO": 0.3, "REQUIRES": 0.3}
DEPENDENCY_TYPES = ("DEFINED_IN", "REFERS_TO", "REQUIRES")
C_MIN = 0.2


def tokens(text: str) -> int:
    return max(1, len(text) // 4)


class ClauseGraph:
    def __init__(self, clauses: dict[str, dict], edges: list[dict], clause_emb: dict[str, np.ndarray], knn: int = 3,
                 token_fn=tokens, edge_cost: dict[str, float] = EDGE_COST, dependency_types=DEPENDENCY_TYPES,
                 seed_only_types=("RELATED_TO", "ALTERNATIVE_OF")):
        self.clauses = clauses
        self.emb = clause_emb
        self.token_fn = token_fn
        self.seed_only_types = tuple(seed_only_types)
        self.out: dict[str, list[tuple[str, str, float]]] = defaultdict(list)
        groups: dict[str, dict[str, set[str]]] = defaultdict(dict)
        for e in edges:
            if e["type"] == "CONTAINS":
                continue
            self.out[e["src"]].append((e["dst"], e["type"], edge_cost.get(e["type"], e.get("weight", 0.5))))
            if e["type"] in dependency_types:
                groups[e["src"]].setdefault(e.get("group", e["dst"]), set()).add(e["dst"])
        ids = list(clause_emb)
        mat = np.stack([clause_emb[i] for i in ids])
        sims = mat @ mat.T
        for a, i in enumerate(ids):
            for b in np.argsort(-sims[a])[1:knn + 1]:
                self.out[i].append((ids[b], "RELATED_TO", float(1.0 - sims[a, b])))
        # cid -> its dependencies; each is a set of nodes, any one of which resolves it
        self.deps: dict[str, list[set[str]]] = {cid: list(groups[cid].values()) for cid in clauses}

    def unresolved(self, cid: str, evidence: set[str]) -> int:
        return sum(1 for group in self.deps.get(cid, ()) if not group & evidence)

    # ------------------------------------------------------------------ strategies
    def bfs(self, seeds: list[str], budget: int, depth: int = 2) -> dict:
        t0 = time.time()
        evidence, used, expanded = [], 0, 0
        seen = set()
        queue = deque((s, 0) for s in seeds)
        while queue:
            cid, d = queue.popleft()
            if cid in seen:
                continue
            seen.add(cid)
            cost = self.token_fn(self.clauses[cid]["text"])
            if used + cost > budget:
                continue
            evidence.append(cid)
            used += cost
            if d < depth:
                for dst, etype, _ in self.out[cid]:
                    if etype in ("DEFINED_IN", "REFERS_TO"):
                        expanded += 1
                        queue.append((dst, d + 1))
        return dict(evidence=evidence, tokens=used, expanded=expanded, seconds=time.time() - t0)

    def ppr(self, seeds: list[str], seed_scores: list[float], budget: int, alpha: float = 0.85) -> dict:
        t0 = time.time()
        g = nx.Graph()
        g.add_nodes_from(self.clauses)
        for src, outs in self.out.items():
            for dst, _, w in outs:
                g.add_edge(src, dst, weight=1.0 / (0.05 + w))
        pers = {s: max(sc, 1e-6) for s, sc in zip(seeds, seed_scores)}
        pr = nx.pagerank(g, alpha=alpha, personalization=pers, weight="weight")
        evidence, used = [], 0
        for cid, _ in sorted(pr.items(), key=lambda x: -x[1]):
            cost = self.token_fn(self.clauses[cid]["text"])
            if used + cost > budget:
                continue
            evidence.append(cid)
            used += cost
            if used >= budget * 0.98:
                break
        return dict(evidence=evidence, tokens=used, expanded=g.number_of_nodes(), seconds=time.time() - t0)

    def astar(self, seeds: list[str], q_emb: np.ndarray, budget: int, lam: float = C_MIN, mu: float = 1.0,
              pinned: bool = False, follow_seed_only: bool = True, present: list[str] = ()) -> dict:
        """README 2.4.2. Seeds start with g = 0. The search stops when every seed is in the evidence
        and no dependency (definition, cross-reference, legal requirement) of the evidence is
        unresolved, or when the budget or frontier runs out. With `pinned`, the seeds are in the evidence
        from the start (their tokens count towards `budget`) and the search only adds their dependencies. With
        `follow_seed_only` false, the seed-only edges (embedding neighbours etc.) are not followed at all.
        `present` (with `pinned`): chunks already in the evidence, after the seeds, that are not searched from;
        they resolve dependencies and count towards `budget`, but their own dependencies don't keep the search going."""
        t0 = time.time()
        cos = {cid: float(self.emb[cid] @ q_emb) for cid in self.clauses}
        evidence: list[str] = []
        ev_set: set[str] = set()
        used, expanded = 0, 0
        frontier: list[tuple[float, int, str, float]] = []
        tie = 0

        def h(cid: str) -> float:
            return lam * (1.0 - cos[cid]) + mu * self.unresolved(cid, ev_set) * C_MIN

        seed_set = set(seeds)
        others = set()
        if pinned:
            evidence = list(dict.fromkeys(seeds))
            others = {p for p in present if p not in seed_set}
            evidence += [p for p in dict.fromkeys(present) if p in others]
            ev_set = set(evidence)
            used = sum(self.token_fn(self.clauses[s]["text"]) for s in evidence)
        for s in seeds:
            heapq.heappush(frontier, (h(s), tie, s, 0.0))
            tie += 1
        while frontier and used < budget:
            f, _, cid, g = heapq.heappop(frontier)
            if cid in ev_set and not (pinned and cid in seed_set and g == 0.0):
                continue
            if cid not in ev_set:
                cost = self.token_fn(self.clauses[cid]["text"])
                if used + cost > budget:
                    continue
                evidence.append(cid)
                ev_set.add(cid)
                used += cost
            if seed_set <= ev_set and all(self.unresolved(e, ev_set) == 0 for e in evidence if e not in others):
                break
            for dst, etype, w in self.out[cid]:
                if dst in ev_set:
                    continue
                # RELATED_TO and ALTERNATIVE_OF (seed_only_types) are only followed from seeds (one hop), dependencies always
                if etype in self.seed_only_types and (cid not in seed_set or not follow_seed_only):
                    continue
                g2 = g + w + self.token_fn(self.clauses[dst]["text"]) / budget
                expanded += 1
                heapq.heappush(frontier, (g2 + h(dst), tie, dst, g2))
                tie += 1
        return dict(evidence=evidence, tokens=used, expanded=expanded, seconds=time.time() - t0)


def graph_metrics(evidence: list[str], graph: ClauseGraph, graded: dict[str, int], relevant_grade: int = 2) -> dict:
    ev = set(evidence)
    operative = [e for e in evidence if graph.clauses[e]["variant"] != "definition"]
    terms = [t for e in operative for t in graph.clauses[e]["uses_terms"]]
    refs = [r for e in evidence for r in graph.clauses[e]["refers_to"]]
    reqs = [d for e in evidence for d, t, _ in graph.out[e] if t == "REQUIRES"]
    rel = [u for u, g in graded.items() if g >= relevant_grade]
    return dict(
        clause_recall=(sum(1 for u in rel if u in ev) / len(rel)) if rel else float("nan"),
        definition_coverage=(sum(1 for t in terms if t in ev) / len(terms)) if terms else 1.0,
        xref_completeness=(sum(1 for r in refs if r in ev) / len(refs)) if refs else 1.0,
        requires_satisfied=(sum(1 for r in reqs if r in ev) / len(reqs)) if reqs else 1.0,
    )
