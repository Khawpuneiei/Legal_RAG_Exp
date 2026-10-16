"""Integration tests of the SQL workflow (db/migrations) on a real PostgreSQL + pgvector.

Run with DATABASE_URL pointing at a disposable database where the migrations were applied (CI does this with a
pgvector service container). Skipped otherwise.
"""
import os
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")
DSN = os.environ.get("DATABASE_URL")
pytestmark = [pytest.mark.postgres, pytest.mark.skipif(not DSN, reason="DATABASE_URL not set")]


@pytest.fixture()
def cur():
    with psycopg.connect(DSN, autocommit=True) as conn, conn.cursor() as c:
        yield c


def call(cur, sql, *args):
    from psycopg.types.json import Jsonb
    cur.execute(sql, tuple(Jsonb(a) if isinstance(a, dict) else a for a in args))
    return cur.fetchone()[0]


DRAFT = dict(mode="rules", config={"policy_sha256": "x"}, fields={"counterparty_name": "Acme"}, selections=[], issues=[], route="escalate")


def test_submit_review_and_audit_chain(cur):
    res = call(cur, "select public.api_submit(%s)", dict(requester="ci", agreement_type="NDA", form={"counterparty_name": "Acme"}, text_masked="x", draft=DRAFT))
    assert res["status"] == "ESCALATED"
    with pytest.raises(psycopg.errors.RaiseException, match="Senior Legal"):
        call(cur, "select public.api_review(%s)", dict(request_id=res["id"], decision="approve", reviewer="j", role="legal_reviewer"))
    out = call(cur, "select public.api_review(%s)", dict(request_id=res["id"], decision="approve", reviewer="s", role="senior_legal"))
    assert out["status"] == "APPROVED"
    full = call(cur, "select public.api_get_request(%s::uuid)", res["id"])
    assert [e["event"] for e in full["audit"]] == ["request_submitted", "draft_generated", "routed", "review_approve"]
    assert call(cur, "select public.api_verify_audit()")["intact"] is True


def test_audit_is_append_only(cur):
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        cur.execute("update public.audit_events set actor = 'x'")
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        cur.execute("delete from public.audit_events")


def test_queue_mode_claim_and_complete(cur):
    res = call(cur, "select public.api_submit(%s)", dict(requester="ci", agreement_type="IMA", form={}, text_masked="x"))
    assert res["status"] == "QUEUED"
    job = None
    for _ in range(50):  # other tests may have queued jobs; take ours
        job = call(cur, "select public.worker_claim()")
        if job is None or job["request_id"] == res["id"]:
            break
        call(cur, "select public.worker_complete(%s)", dict(job_id=job["job_id"], request_id=job["request_id"], draft=dict(DRAFT, route="standard_review")))
    assert job and job["request_id"] == res["id"]
    call(cur, "select public.worker_complete(%s)", dict(job_id=job["job_id"], request_id=res["id"], draft=dict(DRAFT, route="standard_review")))
    assert call(cur, "select public.api_get_request(%s::uuid)", res["id"])["request"]["status"] == "IN_REVIEW"


def test_hybrid_search_returns_fused_ranking(cur):
    cid = "TEST-" + uuid.uuid4().hex[:6].upper()
    vec = "[" + ",".join(["0.051"] * 384) + "]"
    cur.execute("insert into public.clauses (clause_id, version, type, title, variant, templates, body, embedding) "
                "values (%s, 'v1', 'governing_law', 'Governing Law (England)', 'fallback', array['ALL'], 'governed by the laws of England and Wales', %s::extensions.vector)",
                (cid, vec))
    cur.execute("select clause_id from public.hybrid_search('English law governs the contract', %s::extensions.vector, 5, 'NDA')", (vec,))
    assert cid in [r[0] for r in cur.fetchall()]


def test_anon_role_cannot_read_tables(cur):
    cur.execute("set role anon")
    try:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("select * from public.requests")
    finally:
        cur.execute("reset role")
