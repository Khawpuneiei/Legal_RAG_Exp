"""A*-search clause assembly (README section 2.4.3; Exp 2 conditions H3b and H-det).

Each special request ("requirement") must be assigned one approved clause or nothing (= unsupported_clause).
The assignment is found with A* over partial assignments, requirement by requirement:

  option cost   c(r, k) = (1 - s_k) + w_dev * deviation_cost_k       for a candidate clause k
                c(r, -) = tau                                        for "no approved clause"
  conflict      +1 if k has the same clause type as a clause already assigned to another requirement
                (e.g. two governing-law clauses), unless it is the same clause
  g(n)          sum of option and conflict costs of the requirements assigned so far
  h(n)          sum over unassigned requirements of their cheapest option cost (admissible: conflicts only add cost)

s_k is the reranker probability mapped to [0, 1] on a log scale (1e-6 -> 0, 1 -> 1). Candidate actions come from
the retriever rather than from one LLM call per expansion (ToolChain*), to fit the local GPU budget; tau is tuned
on the dev split.
"""
from __future__ import annotations

import heapq
import math
import re

from src.agreement.validation import INJECTION
from src.agreement.library import Library

W_DEV = 0.1


def calibrated(score: float) -> float:
    return min(1.0, max(0.0, (math.log10(max(score, 1e-6)) + 6.0) / 6.0))


def astar_assign(lib: Library, candidates: list[list[dict]], tau: float) -> tuple[list[str | None], int]:
    n = len(candidates)
    opts: list[list[tuple[float, str | None]]] = []
    for cands in candidates:
        o = [((1.0 - calibrated(c["score"])) + W_DEV * c["deviation_cost"], c["clause_id"]) for c in cands]
        o.append((tau, None))
        opts.append(sorted(o, key=lambda x: x[0]))
    min_cost = [o[0][0] for o in opts]
    suffix = [0.0] * (n + 1)
    for i in range(n - 1, -1, -1):
        suffix[i] = suffix[i + 1] + min_cost[i]
    frontier = [(suffix[0], 0.0, 0, 0, ())]
    expanded, tie = 0, 1
    while frontier:
        f, g, _, i, chosen = heapq.heappop(frontier)
        if i == n:
            return list(chosen), expanded
        expanded += 1
        used_types = {lib.clauses[c]["type"]: c for c in chosen if c}
        for cost, cid in opts[i]:
            extra = 0.0
            if cid and lib.clauses[cid]["type"] in used_types and used_types[lib.clauses[cid]["type"]] != cid:
                extra = 1.0
            g2 = g + cost + extra
            heapq.heappush(frontier, (g2 + suffix[i + 1], g2, tie, i + 1, chosen + (cid,)))
            tie += 1
    return [None] * n, expanded


BODY = re.compile(r"Could you prepare|We are discussing|We won a discretionary|Please draft the IMA|wants to distribute|"
                  r"Can we get a distribution|is committing US|New subscription from|Please prepare the subscription|"
                  r"It should take effect", re.I)
CLOSER = re.compile(r"^(Thanks|Many thanks|Appreciate it|Cheers)|\((Sales|Ops|IR|Distribution|PM team|Product)\)$", re.I)
OPENER = re.compile(r"^(Hi|Hello|Dear|Morning)\b[^.?!]*,?$", re.I)


def rule_requirements(text: str) -> list[str]:
    """No-LLM requirement segmentation for H-det: the sentences that are not greeting, request body, sign-off,
    a date statement or an injection. Written against the dev phrasing, so it is optimistic on this synthetic set."""
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    out = []
    for s in sents:
        if BODY.search(s) or CLOSER.search(s) or OPENER.match(s) or INJECTION.search(s):
            continue
        if len(s.split()) < 4:
            continue
        out.append(s)
    return out
