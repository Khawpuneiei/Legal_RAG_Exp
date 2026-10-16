"""Web app and workflow tests with the in-memory store and keyword search (no network, no model)."""
import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("STORE", "memory")
os.environ.setdefault("SEARCH", "keyword")
os.environ.setdefault("DRAFTING_MODE", "rules")

from fastapi.testclient import TestClient  # noqa: E402

from src.app import pii  # noqa: E402
from src.app.main import app  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ITEMS = {r["request_id"]: r for r in (json.loads(x) for x in (ROOT / "data" / "synthetic" / "intake.jsonl").read_text(encoding="utf-8").splitlines() if x.strip())}
client = TestClient(app)


def submit(rid: str) -> dict:
    it = ITEMS[rid]
    r = client.post("/api/v1/requests", json=dict(agreement_type=it["agreement_type"], form={k: v for k, v in it["form"].items() if k != "agreement_type"},
                                                  text=it["text"], requester="pytest"))
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.parametrize("path", ["/", "/requests/new", "/requests/new?sample=REQ-022", "/queue", "/audit", "/scoreboard", "/architecture",
                                  "/governance", "/healthz", "/api/v1/version", "/api/docs", "/seed/library.json"])
def test_pages_render(path):
    assert client.get(path).status_code == 200


def test_security_headers():
    h = client.get("/").headers
    assert "default-src 'self'" in h["content-security-policy"]
    assert h["x-frame-options"] == "DENY" and h["x-content-type-options"] == "nosniff"
    assert h["x-request-id"]


def test_injection_is_flagged_and_escalated():
    d = submit("REQ-022")
    assert d["draft"]["route"] == "escalate"
    assert "prompt_injection" in [i["type"] for i in d["draft"]["issues"]]
    assert d["request"]["status"] == "ESCALATED"


def test_data_problem_returns_to_requester():
    d = submit("REQ-042")  # SIDE letter with no effective date
    assert d["draft"]["route"] == "return_to_requester"
    assert d["request"]["status"] == "RETURNED"


def test_review_permissions_and_audit_chain():
    d = submit("REQ-022")
    rid = d["request"]["id"]
    r = client.post(f"/api/v1/requests/{rid}/review", json=dict(decision="approve", reviewer="junior", role="legal_reviewer"))
    assert r.status_code == 409 and "Senior Legal" in r.json()["detail"]
    r = client.post(f"/api/v1/requests/{rid}/review", json=dict(decision="approve", reviewer="senior", role="senior_legal"))
    assert r.status_code == 200 and r.json()["status"] == "APPROVED"
    r = client.post(f"/api/v1/requests/{rid}/review", json=dict(decision="reject", reviewer="senior", role="senior_legal"))
    assert r.status_code == 409  # final states cannot be reviewed again
    assert client.get("/api/v1/audit/verify").json()["intact"] is True
    events = [e["event"] for e in client.get(f"/api/v1/requests/{rid}").json()["audit"]]
    assert events[:3] == ["request_submitted", "draft_generated", "routed"] and events[-1] == "review_approve"


def test_requester_cannot_review():
    rid = submit("REQ-005")["request"]["id"]
    r = client.post(f"/api/v1/requests/{rid}/review", json=dict(decision="approve", reviewer="me", role="requester"))
    assert r.status_code == 422  # rejected by the API schema before reaching the store


def test_docx_download():
    rid = submit("REQ-005")["request"]["id"]
    r = client.get(f"/requests/{rid}/draft.docx")
    assert r.status_code == 200 and r.content[:2] == b"PK"


def test_html_form_flow_and_pii_masking():
    r = client.post("/requests", data={"agreement_type": "NDA", "NDA__counterparty_name": "Acme Pte Ltd", "NDA__governing_law": "Singapore",
                                       "text": "Please prepare an NDA with Acme Pte Ltd. Contact a.b@example.com or +65 9123 4567, NRIC S1234567D."},
                    follow_redirects=False)
    assert r.status_code == 303
    page = client.get(r.headers["location"]).text
    assert "[EMAIL]" in page and "[NRIC_FIN]" in page and "a.b@example.com" not in page


def test_pii_mask_counts():
    masked, found = pii.mask("call 81234567, email x@y.com, account no 1234567890")
    assert found == {"EMAIL": 1, "PHONE_SG": 1, "BANK_ACCOUNT": 1}
    assert "81234567" not in masked


def test_cross_origin_post_blocked():
    r = client.post("/requests", data={"agreement_type": "NDA"}, headers={"origin": "https://evil.example"}, follow_redirects=False)
    assert r.status_code == 403
