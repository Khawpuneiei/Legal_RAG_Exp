"""Shared data structures, dataset loaders and a small on-disk cache."""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = ROOT / ".cache"


@dataclass
class Unit:
    """A gold-labelled region of a document (a clause). One unit id may occur in several documents."""
    unit_id: str
    doc_id: str
    start: int
    end: int


@dataclass
class Query:
    qid: str
    text: str
    graded: dict[str, int] = field(default_factory=dict)   # unit_id -> grade (higher is better)
    spans: list[tuple[str, int, int]] = field(default_factory=list)  # gold character spans (doc_id, start, end)
    tags: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


@dataclass
class Dataset:
    name: str
    documents: dict[str, str]
    queries: list[Query]
    units: list[Unit] = field(default_factory=list)
    relevant_grade: int = 2          # grade at or above which a unit counts as relevant
    weights: dict[str, float] = field(default_factory=dict)  # per-query weight (LegalBench-RAG)
    meta: dict = field(default_factory=dict)


def read_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def stable_hash(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:24]


def load_synthetic(split: str | None = None) -> Dataset:
    base = DATA / "synthetic"
    docs = read_jsonl(base / "documents.jsonl")
    clauses = {c["clause_id"]: c for c in read_jsonl(base / "clauses.jsonl")}
    documents = {d["doc_id"]: d["text"] for d in docs}
    units = [Unit(s["clause_id"], d["doc_id"], s["start"], s["end"]) for d in docs for s in d["spans"]]
    first_span = {}
    for u in units:
        first_span.setdefault(u.unit_id, u)
    queries = []
    for r in read_jsonl(base / "requests.jsonl"):
        if split and r["split"] != split:
            continue
        spans = []
        for cid, g in r["gold"].items():
            if g >= 3:
                spans += [(u.doc_id, u.start, u.end) for u in units if u.unit_id == cid]
        queries.append(Query(r["request_id"], r["text"], dict(r["gold"]), spans, [r["agreement_type"]],
                             dict(asks=r["asks"], missing_asks=r["missing_asks"], split=r["split"], agreement_type=r["agreement_type"])))
    return Dataset("synthetic", documents, queries, units, relevant_grade=2, meta=dict(clauses=clauses))


def load_acord(split: str = "test") -> Dataset:
    base = DATA / "public" / "acord"
    corpus = read_jsonl(base / "corpus.jsonl")
    documents = {c["_id"]: c["text"] for c in corpus}
    units = [Unit(cid, cid, 0, len(t)) for cid, t in documents.items()]
    qtext = {q["_id"]: q["text"] for q in read_jsonl(base / "queries.jsonl")}
    graded: dict[str, dict[str, int]] = {}
    with open(base / "qrels" / f"{split}.tsv", encoding="utf-8") as f:
        for row in csv.reader(f, delimiter="\t"):
            if row[0] == "query-id":
                continue
            graded.setdefault(row[0], {})[row[1]] = int(row[2])
    queries = [Query(qid, qtext[qid], g) for qid, g in sorted(graded.items())]
    # ACORD grades: 0..4 (= 1..5 stars). 3 = 4-star (relevant, minor omissions).
    # Unjudged pairs are ignored in evaluation (paper, appendix C.5), so rankings must be deep enough
    # to contain at least ten judged clauses: retrieve the top 1,000 instead of the top 100.
    return Dataset(f"acord-{split}", documents, queries, units, relevant_grade=3,
                   meta=dict(judged_only=True, top_n=1000))


def _safe_name(rel_path: str) -> str:
    """Same mapping as scripts/download_public.py (MAUD file names contain '|')."""
    bad = '<>:"|?*'
    return "".join(f"%{ord(c):02X}" if c in bad else c for c in rel_path)


def load_lbr(subset: str = "mini") -> Dataset:
    base = DATA / "public" / "legalbenchrag"
    mini = json.loads((base / "mini.json").read_text(encoding="utf-8"))
    documents = {d: (base / "mirror" / "corpus" / _safe_name(d)).read_text(encoding="utf-8") for d in mini["documents"]}
    queries, weights = [], {}
    counts: dict[str, int] = {}
    for t in mini["tests"]:
        counts[t["tags"][0]] = counts.get(t["tags"][0], 0) + 1
    for i, t in enumerate(mini["tests"]):
        qid = f"LBR-{i:04d}"
        spans = [(s["file_path"], s["span"][0], s["span"][1]) for s in t["snippets"]]
        queries.append(Query(qid, t["query"], {}, spans, t["tags"]))
        weights[qid] = 0.25 / counts[t["tags"][0]]  # each of the 4 datasets weighted equally (official script)
    return Dataset("lbr-mini", documents, queries, [], weights=weights)


class JsonCache:
    """Append-only JSON-lines cache keyed by a hash (LLM outputs)."""

    def __init__(self, name: str):
        self.path = CACHE / f"{name}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data: dict[str, object] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self.data[rec["k"]] = rec["v"]

    def get(self, key: str):
        return self.data.get(key)

    def put(self, key: str, value) -> None:
        self.data[key] = value
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"k": key, "v": value}, ensure_ascii=False) + "\n")
