"""Workflow store adapters. All of them call the same SQL api_* functions (db/migrations), except MemoryStore,
which mirrors their behaviour in Python for local development and unit tests without a database."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import threading
import uuid

import requests


class StoreError(ValueError):
    """A rule enforced by the database (invalid transition, permission, rate limit)."""


class SupabaseStore:
    name = "supabase"

    def __init__(self, url: str, key: str, timeout: int = 20):
        self.base = url.rstrip("/") + "/rest/v1/rpc/"
        self.headers = {"apikey": key, "Content-Type": "application/json", "Accept": "application/json"}
        self.timeout = timeout
        self.session = requests.Session()

    def _rpc(self, fn: str, body: dict):
        r = self.session.post(self.base + fn, json=body, headers=self.headers, timeout=self.timeout)
        if r.status_code >= 400:
            try:
                msg = r.json().get("message") or r.text
            except ValueError:
                msg = r.text
            if r.status_code >= 500 and "exception" not in msg.lower():
                raise RuntimeError(f"store unavailable ({r.status_code})")
            raise StoreError(msg[:300])
        return r.json()

    def submit(self, p: dict) -> dict:
        return self._rpc("api_submit", {"p": p})

    def review(self, p: dict) -> dict:
        return self._rpc("api_review", {"p": p})

    def get(self, rid: str) -> dict | None:
        try:
            uuid.UUID(rid)
        except ValueError:
            return None
        return self._rpc("api_get_request", {"p_id": rid})

    def list(self, status: str | None = None, limit: int = 50) -> list:
        return self._rpc("api_list_requests", {"p_status": status, "p_limit": limit}) or []

    def audit(self, limit: int = 100) -> list:
        return self._rpc("api_list_audit", {"p_limit": limit}) or []

    def verify_audit(self) -> dict:
        return self._rpc("api_verify_audit", {})

    def stats(self) -> dict:
        return self._rpc("api_stats", {})

    def ping(self) -> bool:
        self.stats()
        return True


class PostgresStore:
    """Direct Postgres (Kubernetes). DATABASE_URL comes from a Secret; the role only has EXECUTE on api_*/worker_*."""
    name = "postgres"

    def __init__(self, dsn: str):
        from psycopg_pool import ConnectionPool
        self.pool = ConnectionPool(dsn, min_size=1, max_size=int(__import__("os").environ.get("DB_POOL_MAX", "5")), open=True)

    def _call(self, sql: str, args: tuple = ()):
        import psycopg
        from psycopg.types.json import Jsonb
        args = tuple(Jsonb(a) if isinstance(a, dict) else a for a in args)
        try:
            with self.pool.connection() as conn, conn.cursor() as cur:
                cur.execute(sql, args)
                row = cur.fetchone()
                return row[0] if row else None
        except psycopg.errors.RaiseException as e:
            raise StoreError(str(e).split("\n")[0]) from e

    def submit(self, p):
        return self._call("select public.api_submit(%s)", (p,))

    def review(self, p):
        return self._call("select public.api_review(%s)", (p,))

    def get(self, rid):
        try:
            uuid.UUID(rid)
        except ValueError:
            return None
        return self._call("select public.api_get_request(%s::uuid)", (rid,))

    def list(self, status=None, limit=50):
        return self._call("select public.api_list_requests(%s, %s)", (status, limit)) or []

    def audit(self, limit=100):
        return self._call("select public.api_list_audit(%s)", (limit,)) or []

    def verify_audit(self):
        return self._call("select public.api_verify_audit()")

    def stats(self):
        return self._call("select public.api_stats()")

    def worker_claim(self):
        return self._call("select public.worker_claim()")

    def worker_complete(self, p):
        return self._call("select public.worker_complete(%s)", (p,))

    def search(self, query_text: str, embedding: list[float], k: int, agreement_type: str | None):
        vec = "[" + ",".join(f"{x:.6f}" for x in embedding) + "]"
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute("select clause_id, title, variant, deviation_cost, similarity, rrf_score from public.hybrid_search(%s, %s::extensions.vector, %s, %s)",
                        (query_text, vec, k, agreement_type))
            cols = ["clause_id", "title", "variant", "deviation_cost", "similarity", "rrf_score"]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def ping(self) -> bool:
        self._call("select 1")
        return True


class MemoryStore:
    """In-process store with the same transitions and hash-chained audit as the SQL functions."""
    name = "memory"

    def __init__(self):
        self.lock = threading.Lock()
        self.requests: dict[str, dict] = {}
        self.drafts: dict[str, dict] = {}
        self.reviews: list[dict] = []
        self.events: list[dict] = []

    def _now(self):
        return dt.datetime.now(dt.UTC).isoformat()

    def _audit(self, rid, actor, role, event, details):
        prev = self.events[-1]["hash"] if self.events else None
        at = self._now()
        h = hashlib.sha256(f"{prev or ''}|{at}|{rid or ''}|{actor}|{role}|{event}|{json.dumps(details, sort_keys=True)}".encode()).hexdigest()
        self.events.append(dict(id=len(self.events) + 1, at=at, request_id=rid, actor=actor, actor_role=role, event=event, details=details, prev_hash=prev, hash=h))

    def submit(self, p):
        with self.lock:
            if not p.get("requester") or not p.get("agreement_type"):
                raise StoreError("requester and agreement_type are required")
            rid = str(uuid.uuid4())
            ref = "REQ-" + dt.datetime.now().strftime("%y%m%d") + "-" + rid[:5].upper()
            d = p.get("draft")
            status = "QUEUED" if d is None else {"escalate": "ESCALATED", "return_to_requester": "RETURNED"}.get(d["route"], "IN_REVIEW")
            self.requests[rid] = dict(id=rid, ref=ref, created_at=self._now(), updated_at=self._now(), requester=p["requester"],
                                      agreement_type=p["agreement_type"], form=p.get("form", {}), text_masked=p.get("text_masked", ""),
                                      pii_findings=p.get("pii_findings", {}), status=status, route=d["route"] if d else None, draft_version=1 if d else 0)
            self._audit(rid, p["requester"], p.get("role", "requester"), "request_submitted", dict(ref=ref, agreement_type=p["agreement_type"]))
            if d:
                self.drafts[rid] = dict(d, version=1, request_id=rid, created_at=self._now())
                self._audit(rid, "drafting-engine", "system", "draft_generated", dict(version=1, mode=d.get("mode"), config=d.get("config")))
                self._audit(rid, "routing-policy", "system", "routed", dict(route=d["route"]))
            return dict(id=rid, ref=ref, status=status, route=d["route"] if d else None)

    def review(self, p):
        with self.lock:
            r = self.requests.get(p.get("request_id"))
            if not r:
                raise StoreError("request not found")
            role, decision = p.get("role"), p.get("decision")
            if role not in ("legal_reviewer", "senior_legal"):
                raise StoreError("only Legal can review drafts")
            if r["status"] not in ("IN_REVIEW", "ESCALATED"):
                raise StoreError(f"request is {r['status']} and cannot be reviewed")
            if decision == "approve" and r["status"] == "ESCALATED" and role != "senior_legal":
                raise StoreError("escalated drafts must be approved by Senior Legal / Compliance")
            new = {"approve": "APPROVED", "reject": "REJECTED", "request_changes": "RETURNED", "escalate": "ESCALATED"}.get(decision)
            if not new:
                raise StoreError(f"unknown decision {decision}")
            self.reviews.append(dict(request_id=r["id"], draft_version=r["draft_version"], reviewer=p.get("reviewer"), reviewer_role=role,
                                     decision=decision, comment=(p.get("comment") or "")[:2000], created_at=self._now()))
            old = r["status"]
            r["status"] = new
            if decision == "escalate":
                r["route"] = "escalate"
            self._audit(r["id"], p.get("reviewer") or "unknown", role, "review_" + decision, dict(comment=(p.get("comment") or "")[:300], to=new, **{"from": old}))
            return dict(id=r["id"], status=new)

    def get(self, rid):
        r = self.requests.get(rid)
        if not r:
            return None
        return dict(request=r, draft=self.drafts.get(rid), reviews=[v for v in self.reviews if v["request_id"] == rid],
                    audit=[e for e in self.events if e["request_id"] == rid])

    def list(self, status=None, limit=50):
        rows = [dict(id=r["id"], ref=r["ref"], created_at=r["created_at"], requester=r["requester"], agreement_type=r["agreement_type"],
                     status=r["status"], route=r["route"], counterparty=r["form"].get("counterparty_name"),
                     n_issues=len((self.drafts.get(r["id"]) or {}).get("issues", [])))
                for r in self.requests.values() if status is None or r["status"] == status]
        return sorted(rows, key=lambda x: x["created_at"], reverse=True)[:limit]

    def audit(self, limit=100):
        refs = {k: v["ref"] for k, v in self.requests.items()}
        return [dict(e, ref=refs.get(e["request_id"])) for e in reversed(self.events[-limit:])]

    def verify_audit(self):
        prev = None
        for e in self.events:
            h = hashlib.sha256(f"{prev or ''}|{e['at']}|{e['request_id'] or ''}|{e['actor']}|{e['actor_role']}|{e['event']}|{json.dumps(e['details'], sort_keys=True)}".encode()).hexdigest()
            if h != e["hash"] or e["prev_hash"] != prev:
                return dict(intact=False, broken_at=e["id"])
            prev = e["hash"]
        return dict(intact=True, checked=len(self.events))

    def stats(self):
        by_status, by_route = {}, {}
        for r in self.requests.values():
            by_status[r["status"]] = by_status.get(r["status"], 0) + 1
            by_route[r["route"] or "none"] = by_route.get(r["route"] or "none", 0) + 1
        return dict(by_status=by_status, by_route=by_route, requests=len(self.requests), audit_events=len(self.events), clauses=None, clauses_indexed=None)

    def ping(self):
        return True
