"""PII Guard (plan component 2): mask personal identifiers in free text before storage or any external LLM call.

Regex recognisers for Singapore identifiers (NRIC/FIN, UEN), emails, phone numbers and bank account numbers. Names
of the counterparty stay (they are needed for drafting and are entity, not personal, data in most requests); in
production this module is swapped for Microsoft Presidio with these patterns as custom recognisers.
Only the counts of what was masked are logged, never the values.
"""
from __future__ import annotations

import re

PATTERNS = {
    "NRIC_FIN": re.compile(r"\b[STFGM]\d{7}[A-Z]\b"),
    "EMAIL": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "PHONE_SG": re.compile(r"(?:\+65[\s-]?)?\b[689]\d{3}[\s-]?\d{4}\b"),
    "BANK_ACCOUNT": re.compile(r"\b\d{3}-\d{5,6}-\d{1,3}\b|\b(?:account|a/c)\s*(?:no\.?|number)?\s*:?\s*\d{7,14}\b", re.I),
    "UEN": re.compile(r"\b(?:\d{8}[A-Z]|\d{9}[A-Z]|[TSR]\d{2}[A-Z]{2}\d{4}[A-Z])\b"),
}


def mask(text: str) -> tuple[str, dict[str, int]]:
    found: dict[str, int] = {}
    out = text
    for name, rx in PATTERNS.items():
        out, n = rx.subn(f"[{name}]", out)
        if n:
            found[name] = n
    return out, found
