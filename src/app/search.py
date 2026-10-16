"""Clause search backends. All return [{clause_id, title, variant, deviation_cost, relevance (0-1), ...}] so the A*
assembler and the agent tools work with any of them; each carries its own abstention threshold tau (tuned on dev)."""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

import requests

from src.agreement.library import load_library

ROOT = Path(__file__).resolve().parents[2]
CALIBRATION = ROOT / "configs" / "search_calibration.json"


def _calibration(name: str) -> dict:
    try:
        return json.loads(CALIBRATION.read_text(encoding="utf-8")).get(name, {})
    except (OSError, ValueError):
        return {}


def _relevance(sim: float, lo: float, hi: float) -> float:
    return min(1.0, max(0.0, (sim - lo) / max(hi - lo, 1e-6)))


class SupabaseSearch:
    """gte-small embeddings in a Supabase Edge Function + hybrid_search() in Postgres (full text + pgvector, RRF)."""
    name = "supabase-hybrid-gte-small"

    def __init__(self, url: str, anon_jwt: str, publishable_key: str, timeout: int = 20):
        self.endpoint = url.rstrip("/") + "/functions/v1/clause-search"
        self.headers = {"Content-Type": "application/json", "apikey": publishable_key}
        if anon_jwt:
            self.headers["Authorization"] = f"Bearer {anon_jwt}"
        self.timeout = timeout
        cal = _calibration(self.name)
        self.lo, self.hi, self.tau = cal.get("lo", 0.78), cal.get("hi", 0.92), cal.get("tau", 0.7)
        self.session = requests.Session()
        self._cache: dict = {}

    def search(self, query: str, k: int = 5, agreement_type: str | None = None) -> list[dict]:
        key = (query, k, agreement_type)
        if key in self._cache:
            return self._cache[key]
        r = self.session.post(self.endpoint, json=dict(query=query[:2000], k=k, agreement_type=agreement_type), headers=self.headers, timeout=self.timeout)
        r.raise_for_status()
        out = [dict(h, relevance=_relevance(float(h.get("similarity") or 0), self.lo, self.hi), score=float(h.get("similarity") or 0))
               for h in r.json().get("results", [])]
        if len(self._cache) < 512:
            self._cache[key] = out
        return out

    def ping(self) -> bool:
        return bool(self.search("governing law", k=1) is not None)


class PostgresSearch:
    """Kubernetes: TEI (gte-small) for the query embedding, hybrid_search() through the Postgres store."""
    name = "postgres-hybrid-gte-small"

    def __init__(self, store, embed_url: str, timeout: int = 10):
        self.store, self.embed_url, self.timeout = store, embed_url.rstrip("/"), timeout
        cal = _calibration("supabase-hybrid-gte-small")   # same model, same calibration
        self.lo, self.hi, self.tau = cal.get("lo", 0.78), cal.get("hi", 0.92), cal.get("tau", 0.7)

    def search(self, query: str, k: int = 5, agreement_type: str | None = None) -> list[dict]:
        r = requests.post(self.embed_url + "/embed", json={"inputs": query[:2000], "normalize": True}, timeout=self.timeout)
        r.raise_for_status()
        emb = r.json()[0]
        rows = self.store.search(query, emb, k, agreement_type)
        return [dict(h, relevance=_relevance(float(h["similarity"] or 0), self.lo, self.hi), score=float(h["similarity"] or 0)) for h in rows]

    def ping(self) -> bool:
        return requests.get(self.embed_url + "/health", timeout=self.timeout).ok


class LocalSearch:
    """The Experiment 3 winner (R5: BGE-M3 hybrid + bge-reranker-v2-m3 + contextual chunks); needs the experiments extra."""
    name = "local-r5-bge-m3-rerank"

    def __init__(self):
        from src.drafting.assembly import calibrated
        from src.retrieval.service import ClauseSearch
        self.inner = ClauseSearch()
        self._cal = calibrated
        try:
            self.tau = json.loads((ROOT / "eval" / "results" / "exp2" / "tau.json").read_text())["H-det"]
        except (OSError, KeyError, ValueError):
            self.tau = 0.7

    def search(self, query: str, k: int = 5, agreement_type: str | None = None) -> list[dict]:
        return [dict(h, relevance=self._cal(h["score"])) for h in self.inner.search(query, k=k, agreement_type=agreement_type)]

    def ping(self) -> bool:
        return True


_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = set("a an and are as at be by for from has have in is it its of on or that the this to was were will with shall any all not no may".split())


class KeywordSearch:
    """Dependency-free BM25 over the bundled library: the fallback when no search service is configured."""
    name = "keyword-bm25"

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        lib = load_library()
        self.lib = lib
        self.ids = list(lib.clauses)
        self.docs = [self._tok(lib.clauses[c]["title"] + " " + lib.clauses[c]["text"]) for c in self.ids]
        self.tf = [Counter(d) for d in self.docs]
        n = len(self.docs)
        df = Counter(t for d in self.docs for t in set(d))
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.avg = sum(len(d) for d in self.docs) / n
        self.k1, self.b = k1, b
        self.tau = _calibration(self.name).get("tau", 0.75)

    @staticmethod
    def _tok(text: str) -> list[str]:
        return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]

    def search(self, query: str, k: int = 5, agreement_type: str | None = None) -> list[dict]:
        q = self._tok(query)
        scores = []
        for i, tf in enumerate(self.tf):
            cid = self.ids[i]
            c = self.lib.clauses[cid]
            if agreement_type and agreement_type not in c["templates"] and "ALL" not in c["templates"]:
                continue
            s = sum(self.idf.get(t, 0) * tf[t] * (self.k1 + 1) / (tf[t] + self.k1 * (1 - self.b + self.b * len(self.docs[i]) / self.avg)) for t in q if t in tf)
            scores.append((s, cid))
        scores.sort(reverse=True)
        top = scores[0][0] if scores and scores[0][0] > 0 else 1.0
        return [dict(clause_id=cid, title=self.lib.clauses[cid]["title"], variant=self.lib.clauses[cid]["variant"],
                     deviation_cost=self.lib.clauses[cid]["deviation_cost"], score=s, relevance=min(1.0, s / 12.0) if top else 0.0)
                for s, cid in scores[:k]]

    def ping(self) -> bool:
        return True
