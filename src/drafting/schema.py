"""Output contract shared by every drafting condition, and tolerant parsing of model output."""
from __future__ import annotations

import json
import re

from src.agreement.fields import normalise_fields

ISSUE_TYPES = ["missing_field", "date_conflict", "out_of_range", "governing_law", "name_mismatch", "unsupported_clause", "prompt_injection"]
ROUTES = ["standard_review", "escalate", "return_to_requester"]
KEYS = ["agreement_type", "fields", "selections", "issues", "route", "reviewer_note"]

OUTPUT_CONTRACT = """Return ONLY one JSON object with exactly these keys:
{"agreement_type": "NDA|IMA|DIST|SIDE|SUBS",
 "fields": {"<field_name>": <value or null>},
 "selections": [{"requirement": "<special request in a few words>", "clause_id": "<a clause_id from the candidate clauses, or null>"}],
 "issues": [{"type": "missing_field|date_conflict|out_of_range|governing_law|name_mismatch|unsupported_clause|prompt_injection", "field": "<field name or null>", "detail": "<one sentence>"}],
 "route": "standard_review|escalate|return_to_requester",
 "reviewer_note": "<at most 60 words for the Legal reviewer>"}
Use snake_case field names (use the form's field names where they exist). "selections" and "issues" may be empty lists."""


def extract_json(text: str) -> dict | None:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, TypeError):
        pass
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def clean_id(raw) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().strip("[]\"' ")
    s = re.sub(r"^clause[_ ]?id\s*:\s*", "", s, flags=re.I).strip()
    if s.lower() in ("", "null", "none", "n/a"):
        return None
    return s.upper()


def parse_draft(text: str) -> dict:
    """Normalised draft: always has every key. raw_fields keeps the model's types for the checklist metric."""
    data = extract_json(text)
    out = dict(valid_json=data is not None, schema_ok=bool(data) and all(k in data for k in KEYS),
               agreement_type=None, fields={}, raw_fields={}, selections=[], issues=[], route=None, reviewer_note="")
    if not data:
        return out
    if isinstance(data.get("draft"), dict):  # an agent may wrap the draft
        data = data["draft"]
    out["agreement_type"] = str(data.get("agreement_type") or "").upper() or None
    raw_fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    out["raw_fields"] = raw_fields
    out["fields"] = normalise_fields(raw_fields)
    for s in data.get("selections") or []:
        if isinstance(s, dict):
            out["selections"].append(dict(requirement=str(s.get("requirement") or ""), clause_id=clean_id(s.get("clause_id"))))
    for i in data.get("issues") or []:
        if isinstance(i, dict) and i.get("type"):
            t = str(i["type"]).strip().lower()
            field = i.get("field")
            out["issues"].append(dict(type=t, field=None if field in (None, "", "null") else str(field), detail=str(i.get("detail") or ""), source="llm"))
    r = str(data.get("route") or "").strip().lower()
    out["route"] = r if r in ROUTES else None
    out["reviewer_note"] = str(data.get("reviewer_note") or "")[:1200]
    return out


def implicit_unsupported(draft: dict) -> list[dict]:
    """A selection with clause_id null means 'no approved clause': the contract treats it as unsupported_clause."""
    return [dict(type="unsupported_clause", field=None, detail=s["requirement"], source="llm-null-selection")
            for s in draft["selections"] if s["clause_id"] is None]
