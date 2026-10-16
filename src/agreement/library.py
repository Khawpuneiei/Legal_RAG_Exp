"""Policy and approved clause library (versioned inputs to every draft)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "configs" / "policy.yaml"
DATA = ROOT / "data" / "synthetic"


def _read_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class Library:
    policy: dict
    policy_sha256: str
    clauses: dict[str, dict]
    documents: dict[str, dict]
    edges: list[dict]
    library_sha256: str
    standard: dict[str, list[str]] = field(default_factory=dict)   # agreement type -> clause ids in the template
    allowed: dict[str, set[str]] = field(default_factory=dict)     # agreement type -> clause ids usable in that type
    requires: dict[str, set[str]] = field(default_factory=dict)    # clause id -> clause ids it legally requires

    @property
    def types(self) -> list[str]:
        return list(self.policy["agreement_types"])

    def required_fields(self, agreement_type: str) -> list[str]:
        return list(self.policy["agreement_types"][agreement_type]["required_fields"])

    def title(self, agreement_type: str) -> str:
        return self.policy["agreement_types"][agreement_type]["title"]

    def is_allowed(self, agreement_type: str, clause_id: str) -> bool:
        return clause_id in self.allowed.get(agreement_type, set())


@lru_cache(maxsize=1)
def load_library() -> Library:
    policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    clauses = {c["clause_id"]: c for c in _read_jsonl(DATA / "clauses.jsonl")}
    documents = {d["doc_id"]: d for d in _read_jsonl(DATA / "documents.jsonl")}
    edges = _read_jsonl(DATA / "edges.jsonl")
    h = hashlib.sha256()
    for name in ("clauses.jsonl", "documents.jsonl", "edges.jsonl"):
        h.update((DATA / name).read_bytes())
    lib = Library(policy=policy, policy_sha256=file_sha256(POLICY_PATH), clauses=clauses, documents=documents, edges=edges,
                  library_sha256=h.hexdigest())
    for t in policy["agreement_types"]:
        tid = policy["agreement_types"][t]["template_id"]
        lib.standard[t] = [e["dst"] for e in edges if e["src"] == tid and e["type"] == "CONTAINS"
                           and clauses[e["dst"]]["variant"] in ("definition", "standard")]
        lib.allowed[t] = {cid for cid, c in clauses.items() if t in c.get("templates", []) or "ALL" in c.get("templates", [])}
    for e in edges:
        if e["type"] == "REQUIRES":
            lib.requires.setdefault(e["src"], set()).add(e["dst"])
    return lib
