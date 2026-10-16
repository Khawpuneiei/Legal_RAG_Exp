"""Validation Engine and Routing Policy (plan section 4.2, components 7 and 8).

The validator checks the *request* (form + free text) and the draft's clause selections with plain rules, so it runs
independently of the drafting LLM (plan section 12: "validators run independently of the drafting LLM"). Its issues
use the taxonomy in configs/policy.yaml. Checks that need language understanding (asks with no approved clause)
are left to the LLM or to retrieval thresholds.
"""
from __future__ import annotations

import datetime as dt
import re

from src.agreement.fields import DATE_IN_TEXT, ENGLISH_LAW_TEXT, is_null, norm_law, norm_text, normalise, parse_date
from src.agreement.library import Library

INJECTION = re.compile(r"automated drafting system|instruction to the AI|ignore (your|all|previous)|system note|"
                       r"skip (the )?(review|validation)|pre-approved|set the route|mark it as standard|do not raise any issues|"
                       r"send straight for signature", re.I)
ROUTE_ORDER = {"standard_review": 0, "return_to_requester": 1, "escalate": 2}


def issue(type_: str, detail: str, field: str | None = None, source: str = "rules") -> dict:
    d = dict(type=type_, detail=detail, source=source)
    if field:
        d["field"] = field
    return d


def check_request(lib: Library, agreement_type: str, form: dict, text: str) -> list[dict]:
    """Rule checks on the request itself (form + text)."""
    pol = lib.policy
    out: list[dict] = []
    if agreement_type not in pol["agreement_types"]:
        return [issue("missing_field", "agreement type not provided or unknown", "agreement_type")]
    f = {k: normalise(k, v) for k, v in form.items()}
    from src.agreement.fields import extract_from_text
    extracted = extract_from_text(agreement_type, text)
    for name in lib.required_fields(agreement_type):
        if is_null(f.get(name)) and is_null(extracted.get(name)):
            out.append(issue("missing_field", f"{name} is required but not provided", name))
    # ranges
    for name, (lo, hi) in pol["ranges"].items():
        v = f.get(name)
        if v is not None and isinstance(v, float) and not (lo <= v <= hi):
            out.append(issue("out_of_range", f"{name} = {v:g} is outside the approved range {lo}-{hi}", name))
    # dates
    sign = f.get("target_signing_date")
    date_field = "dealing_date" if agreement_type == "SUBS" else "effective_date"
    start = f.get(date_field)
    if sign and start:
        ds, de = dt.date.fromisoformat(sign), dt.date.fromisoformat(start)
        if de < ds and not pol["dates"]["backdating_allowed"]:
            out.append(issue("date_conflict", f"{date_field} {start} is before the target signing date {sign} (backdating)", date_field))
        elif (de - ds).days > pol["dates"]["max_days_after_signing"]:
            out.append(issue("date_conflict", f"{date_field} {start} is more than {pol['dates']['max_days_after_signing']} days after signing", date_field))
    m = DATE_IN_TEXT.search(text)
    if m and start:
        stated = parse_date(m.group(1))
        if stated and stated != start:
            out.append(issue("date_conflict", f"the request text says {stated} but the form says {start}", date_field))
    # governing law
    law = f.get("governing_law")
    approved = [pol["governing_law"]["standard"], *pol["governing_law"]["approved_fallbacks"]]
    if law is not None and law not in approved:
        out.append(issue("governing_law", f"{law} law is not an approved governing law", "governing_law"))
    elif law == "Singapore" and ENGLISH_LAW_TEXT.search(text):
        out.append(issue("governing_law", "the form says Singapore law but the request text asks for English law", "governing_law"))
    # counterparty name must appear in the free text
    name = form.get("counterparty_name")
    if name and norm_text(name) not in norm_text(text):
        out.append(issue("name_mismatch", f"counterparty '{name}' on the form does not appear in the request text", "counterparty_name"))
    # prompt injection
    if INJECTION.search(text):
        out.append(issue("prompt_injection", "the request text contains instructions addressed to the drafting system"))
    return out


def check_selections(lib: Library, agreement_type: str, clause_ids: list[str]) -> tuple[list[dict], dict]:
    """Clause checks: invented or wrong-template ids, unmet legal requirements, material deviations."""
    feedback: list[dict] = []
    valid = []
    for cid in clause_ids:
        if cid not in lib.clauses:
            feedback.append(issue("invalid_clause", f"clause_id {cid} does not exist in the approved library"))
        elif not lib.is_allowed(agreement_type, cid):
            feedback.append(issue("invalid_clause", f"clause_id {cid} is not approved for a {agreement_type}"))
        else:
            valid.append(cid)
    present = set(valid) | set(lib.standard.get(agreement_type, []))
    for cid in valid:
        for dep in lib.requires.get(cid, set()) - present:
            feedback.append(issue("missing_dependency", f"{cid} requires {dep}, which is not in the draft"))
    devs = {cid: lib.clauses[cid]["deviation_cost"] for cid in valid if lib.clauses[cid]["deviation_cost"]}
    thr = lib.policy["material_deviation_cost"]
    material = {cid: c for cid, c in devs.items() if c >= thr}
    return feedback, dict(valid=valid, deviations=devs, material=material)


def route(lib: Library, issues: list[dict], material_deviation: bool) -> str:
    types = {i["type"] for i in issues}
    r = lib.policy["routing"]
    if types & set(r["escalate_on"]) or material_deviation:
        return "escalate"
    if types & set(r["return_on"]):
        return "return_to_requester"
    return "standard_review"


def merge_issues(*lists: list[dict]) -> list[dict]:
    """Union of issue lists, one per (type, field)."""
    seen, out = set(), []
    for lst in lists:
        for i in lst or []:
            key = (i.get("type"), i.get("field") if i.get("type") != "unsupported_clause" else i.get("detail", "")[:40])
            if key not in seen:
                seen.add(key)
                out.append(i)
    return out


def guard_route(policy_route: str, llm_route: str | None) -> str:
    """An LLM may escalate further than the policy, never less (H4 router guard)."""
    if llm_route not in ROUTE_ORDER:
        return policy_route
    return max(policy_route, llm_route, key=lambda r: ROUTE_ORDER[r])


def law_of(v) -> str | None:
    return norm_law(v)
