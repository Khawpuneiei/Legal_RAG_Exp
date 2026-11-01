"""Cross-reference graph over the tax chunks, for A* evidence expansion (Experiment 3 R6 on TaxRAG).

Nodes are the structured chunks (Act subsections, guide paragraphs). Edges, src -> dst:

* REFERS_TO      "subsection (4)" inside an Act section -> that subsection; "subsection (1) of section 37B" ->
                 s 37B(1); "paragraph 6.1" inside a guide -> that paragraph; and each section in the chunk's
                 `cross_refs` (the teammate's detector: "section 37B") -> any chunk of that section.
* DEFINED_IN     an Act subsection -> the subsection of its section that defines its terms ("In this section
                 ...", "In subsection (4) ...", "For the purposes of subsection (7) ...").
* CONTINUES      piece k of a split provision -> piece k - 1.
* INTERPRETED_BY an Act chunk -> the guide paragraphs that cite its section. Not a dependency; followed from
                 seeds only, like the embedding-neighbour RELATED_TO edges that ClauseGraph adds.

REFERS_TO, DEFINED_IN and CONTINUES are dependencies: evidence that contains a chunk but not what it refers to
or is defined by is incomplete. A dependency on a section or a split subsection is resolved by any of its
chunks (the edge's "group").
"""
from __future__ import annotations

import re
from collections import defaultdict

import numpy as np

from src.retrieval.graph import ClauseGraph

EDGE_COST = {"CONTINUES": 0.1, "DEFINED_IN": 0.2, "REFERS_TO": 0.3, "INTERPRETED_BY": 0.3}
DEPENDENCY_TYPES = ("REFERS_TO", "DEFINED_IN", "CONTINUES")
SEED_ONLY = ("RELATED_TO", "INTERPRETED_BY")

_LABELS = r"((?:\(\w+\)(?:\s*(?:,|and|or|to)\s*)?)+)"
SUBSECTION_REF = re.compile(rf"\bsubsections?\s+{_LABELS}(\s+of\s+section\s+(\d+[A-Z]{{0,3}}))?", re.I)
PARA_REF = re.compile(r"\bparagraphs?\s+(\d+\.\d+(?:\s*(?:,|and|or|to)\s*\d+\.\d+)*)", re.I)
LOCAL_DEFINITION = re.compile(r"^(?:In|For the purposes of)\s+(this section|this Part|subsections?\s+" + _LABELS + ")", re.I)


def _labels(text: str) -> list[str]:
    return [lab.upper() if lab[0].isdigit() else lab.lower() for lab in re.findall(r"\((\w+)\)", text)]


def build_edges(chunks: list) -> list[dict]:
    by_id = {c.chunk_id: c for c in chunks}
    by_section: dict[str, list[str]] = defaultdict(list)          # "37B" -> chunk ids
    by_sub: dict[tuple[str, str], list[str]] = defaultdict(list)  # ("37B", "1") -> chunk ids (split pieces)
    by_para: dict[tuple[str, str], list[str]] = defaultdict(list) # ("GR", "6.1") -> chunk ids
    for c in chunks:
        if c.doc_type == "act":
            by_section[c.section].append(c.chunk_id)
            if c.subsection:
                by_sub[(c.section, c.subsection)].append(c.chunk_id)
        else:
            by_para[(c.chunk_id.split(":", 1)[0], c.para)].append(c.chunk_id)
    edges: list[dict] = []

    def add(src: str, dsts: list[str], etype: str, group: str) -> None:
        for dst in dsts:
            if dst != src:
                edges.append(dict(src=src, dst=dst, type=etype, group=group))

    for c in chunks:
        if c.doc_type == "act":
            for m in SUBSECTION_REF.finditer(c.text):
                section = m.group(3) or c.section
                for lab in _labels(m.group(1)):
                    if (section, lab) in by_sub and not (section == c.section and lab == c.subsection):
                        add(c.chunk_id, by_sub[(section, lab)], "REFERS_TO", f"sub:{section}({lab})")
            if c.split_index > 1:
                prev = by_sub.get((c.section, c.subsection)) or by_section[c.section]
                i = prev.index(c.chunk_id)
                if i > 0:
                    add(c.chunk_id, [prev[i - 1]], "CONTINUES", prev[i - 1])
        else:
            doc = c.chunk_id.split(":", 1)[0]
            for m in PARA_REF.finditer(c.text):
                for para in re.findall(r"\d+\.\d+", m.group(1)):
                    if (doc, para) in by_para and para != c.para:
                        add(c.chunk_id, by_para[(doc, para)], "REFERS_TO", f"para:{doc}:{para}")
            if c.split_index > 1:
                prev = by_para[(doc, c.para)]
                i = prev.index(c.chunk_id)
                if i > 0:
                    add(c.chunk_id, [prev[i - 1]], "CONTINUES", prev[i - 1])
        own = c.section if c.doc_type == "act" else None
        for sec in c.cross_refs:
            if sec != own and sec in by_section:
                add(c.chunk_id, by_section[sec], "REFERS_TO", f"sec:{sec}")
                if c.doc_type == "guide":
                    for dst in by_section[sec]:
                        edges.append(dict(src=dst, dst=c.chunk_id, type="INTERPRETED_BY", group=f"guide:{c.chunk_id}"))
    # section-local definitions
    for sec, ids in by_section.items():
        for did in ids:
            m = LOCAL_DEFINITION.match(by_id[did].text.strip())
            if not m:
                continue
            scope = m.group(1).lower()
            if scope.startswith("subsection"):
                targets = [cid for lab in _labels(m.group(2) or "") for cid in by_sub.get((sec, lab), [])]
            elif scope == "this part":
                part = by_id[did].part
                targets = [cid for c2 in chunks if c2.doc_type == "act" and c2.part == part for cid in [c2.chunk_id]]
            else:
                targets = ids
            for cid in targets:
                if cid != did:
                    edges.append(dict(src=cid, dst=did, type="DEFINED_IN", group=did))
    return edges


class TaxGraph:
    """ClauseGraph (the Experiment 3 search) over the tax chunks, with the teammate's token count."""

    def __init__(self, chunks: list, emb: dict[str, np.ndarray], count_tokens, knn: int = 3):
        self.chunks = {c.chunk_id: c for c in chunks}
        self.edges = build_edges(chunks)
        nodes = {c.chunk_id: {"text": c.text} for c in chunks}
        self.graph = ClauseGraph(nodes, self.edges, emb, knn=knn, token_fn=count_tokens, edge_cost=EDGE_COST,
                                 dependency_types=DEPENDENCY_TYPES, seed_only_types=SEED_ONLY)
        self.count_tokens = count_tokens
        self.dep_types: dict[str, dict[str, str]] = defaultdict(dict)     # src -> group -> edge type
        for e in self.edges:
            if e["type"] in DEPENDENCY_TYPES:
                self.dep_types[e["src"]][e["group"]] = e["type"]
        self.groups: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        for e in self.edges:
            if e["type"] in DEPENDENCY_TYPES:
                self.groups[e["src"]][e["group"]].add(e["dst"])

    def completeness(self, evidence: list[str], hits: list[str] | None = None) -> dict:
        """Share of the evidence's dependencies (cross-references, definitions, continuations) resolved in it, and
        their counts. The share's denominator grows with whatever the evidence contains, so with `hits` (the flat
        budgeted hits of the same ranking) it also gives the share of the hits' own dependencies resolved in the
        evidence: a fixed denominator per question, comparable across strategies."""
        ev = set(evidence)
        tally = {t: [0, 0] for t in DEPENDENCY_TYPES}
        for cid in evidence:
            for group, dsts in self.groups.get(cid, {}).items():
                t = self.dep_types[cid][group]
                tally[t][1] += 1
                tally[t][0] += bool(dsts & ev)
        out = {f"{t.lower()}_complete": (a / n if n else 1.0) for t, (a, n) in tally.items()}
        resolved = sum(a for a, _ in tally.values())
        total = sum(n for _, n in tally.values())
        out["dependencies_complete"] = resolved / total if total else 1.0
        out["dependencies_resolved"], out["dependencies_unresolved"] = resolved, total - resolved
        if hits is not None:
            own = [dsts for cid in dict.fromkeys(hits) for dsts in self.groups.get(cid, {}).values()]
            out["hit_dependencies_complete"] = sum(bool(dsts & ev) for dsts in own) / len(own) if own else 1.0
        return out

    def expand(self, hits: list[str], q_emb: np.ndarray, allowance: int, lam: float, mu: float,
               follow_seed_only: bool = True, present: list[str] = ()) -> list[str]:
        """R6x: what A* adds to the hits within `allowance` extra tokens, in the order it adds them. A drop-in for
        the teammate's one-hop `Corpus.expand`, which appends up to 3 cited sections after the hits. R6y
        (`follow_seed_only` false): dependency edges only, without the embedding neighbours and guide paragraphs
        that R6x may also add from the hits. `present`: other chunks already in the evidence; they resolve
        dependencies and cost nothing from the allowance, but the search does not start from them."""
        hits = list(dict.fromkeys(hits))
        others = [c for c in dict.fromkeys(present) if c not in set(hits)]
        used = sum(self.count_tokens(self.chunks[c].text) for c in hits + others)
        out = self.graph.astar(hits, q_emb, used + allowance, lam=lam, mu=mu, pinned=True, follow_seed_only=follow_seed_only,
                               present=others)
        return out["evidence"][len(hits) + len(others):]

    def fill(self, evidence: list[str], ranked: list[str], budget: int) -> list[str]:
        """Top up the evidence with the flat ranking, the teammate's way (stop at the first chunk that does not fit)."""
        out, used = list(evidence), sum(self.count_tokens(self.chunks[c].text) for c in evidence)
        have = set(out)
        for cid in ranked:
            if cid in have:
                continue
            cost = self.count_tokens(self.chunks[cid].text)
            if used + cost > budget:
                break
            out.append(cid)
            have.add(cid)
            used += cost
        return out
