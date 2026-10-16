"""Field normalisation, comparison and rule-based extraction from request text."""
from __future__ import annotations

import datetime as dt
import re

MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september",
                                       "october", "november", "december"], 1)}
MONTHS.update({m[:3]: i for m, i in list(MONTHS.items())})
NULLISH = {"", "null", "none", "n/a", "na", "unknown", "tbc", "tbd", "to be confirmed", "missing", "not provided", "not specified"}
NUMERIC_FIELDS = {"term_months", "management_fee_pct", "performance_fee_pct", "mandate_size_sgd_m", "trailer_fee_pct", "fee_rebate_bps",
                  "commitment_usd_m", "subscription_amount_sgd_m"}
DATE_FIELDS = {"effective_date", "target_signing_date", "dealing_date"}
FIELD_ALIASES = {
    "counterparty": "counterparty_name", "counterparty_legal_name": "counterparty_name", "client_name": "counterparty_name",
    "investor_name": "counterparty_name", "distributor_name": "counterparty_name", "party_name": "counterparty_name",
    "investor_type": "counterparty_type", "client_type": "counterparty_type",
    "law": "governing_law", "governing_law_jurisdiction": "governing_law",
    "start_date": "effective_date", "commencement_date": "effective_date", "signing_date": "target_signing_date",
    "term": "term_months", "duration_months": "term_months", "aum_sgd_m": "mandate_size_sgd_m", "mandate_size": "mandate_size_sgd_m",
    "management_fee": "management_fee_pct", "trailer_fee": "trailer_fee_pct", "fee_rebate": "fee_rebate_bps",
    "commitment": "commitment_usd_m", "commitment_amount_usd_m": "commitment_usd_m", "subscription_amount": "subscription_amount_sgd_m",
    "subscription_sgd_m": "subscription_amount_sgd_m", "fund": "fund_name", "custodian": "custodian_name",
}


def canon_key(k: str) -> str:
    k = re.sub(r"[^a-z0-9]+", "_", str(k).strip().lower()).strip("_")
    return FIELD_ALIASES.get(k, k)


def is_null(v) -> bool:
    return v is None or (isinstance(v, str) and v.strip().lower() in NULLISH)


def parse_date(v) -> str | None:
    if is_null(v):
        return None
    s = str(v).strip()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+),?\s+(\d{4})", s)
        m2 = re.search(r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", s)
        m3 = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)  # Singapore convention dd/mm/yyyy
        if m and m.group(2).lower() in MONTHS:
            d, mo, y = int(m.group(1)), MONTHS[m.group(2).lower()], int(m.group(3))
        elif m2 and m2.group(1).lower() in MONTHS:
            mo, d, y = MONTHS[m2.group(1).lower()], int(m2.group(2)), int(m2.group(3))
        elif m3:
            d, mo, y = map(int, m3.groups())
        else:
            return None
    try:
        return dt.date(y, mo, d).isoformat()
    except ValueError:
        return None


def parse_number(v) -> float | None:
    if is_null(v):
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).lower().replace(",", "")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return None
    x = float(m.group(0))
    if re.search(r"\d\s*(bn|billion)", s):
        x *= 1000.0
    return x


def norm_text(v) -> str:
    s = str(v).lower().replace("’", "'").replace("&", " and ")
    s = re.sub(r"\b(pte|ltd|limited|co|inc|llc|the|a|an)\b\.?", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_law(v) -> str | None:
    if is_null(v):
        return None
    s = str(v).lower()
    if "england" in s or "english" in s or "wales" in s or s.strip() in ("uk", "united kingdom"):
        return "England and Wales"
    if "singapore" in s:
        return "Singapore"
    if "new york" in s:
        return "New York"
    if "hong kong" in s:
        return "Hong Kong"
    return str(v).strip()


def normalise(field: str, v):
    if is_null(v):
        return None
    if field in DATE_FIELDS:
        return parse_date(v)
    if field in NUMERIC_FIELDS:
        return parse_number(v)
    if field == "governing_law":
        return norm_law(v)
    return str(v).strip()


def normalise_fields(raw: dict | None) -> dict:
    out: dict = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        key = canon_key(k)
        if isinstance(v, (dict, list)):
            continue
        out[key] = normalise(key, v)
    return out


def field_matches(field: str, pred, gold) -> bool:
    """Exact match for dates, numbers and law; token containment / Jaccard for free text. Gold None means the value
    cannot be known from the request, so only a null prediction is correct."""
    p = normalise(field, pred)
    g = normalise(field, gold)
    if g is None:
        return p is None
    if p is None:
        return False
    if field in NUMERIC_FIELDS:
        return abs(float(p) - float(g)) < 1e-6
    if field in DATE_FIELDS or field == "governing_law":
        return p == g
    a, b = set(norm_text(p).split()), set(norm_text(g).split())
    if not a or not b:
        return False
    if a <= b or b <= a:
        return len(a & b) >= max(1, min(len(a), len(b)))
    return len(a & b) / len(a | b) >= 0.6


# --------------------------------------------------------------------------------------------- rule-based extraction
DATE_IN_TEXT = re.compile(r"take effect (?:on|from) (\d{1,2} [A-Z][a-z]+ \d{4})")
ENGLISH_LAW_TEXT = re.compile(r"English law|law of England|England and Wales", re.I)
PATTERNS = {
    "purpose": re.compile(r"We are discussing (.+?)\."),
    "strategy": re.compile(r"discretionary (.+?) mandate"),
    "mandate_size_sgd_m": re.compile(r"S\$(\d+(?:\.\d+)?)m"),
    "fund_name": re.compile(r"(?:distribute our|into the) ((?:[A-Z][\w-]*\s?)+?(?:Fund|VCC))"),
    "commitment_usd_m": re.compile(r"US\$(\d+(?:\.\d+)?)m"),
    "subscription_amount_sgd_m": re.compile(r"S\$(\d+(?:\.\d+)?)m"),
}


def extract_from_text(agreement_type: str, text: str) -> dict:
    """Rule-based extractor used by the no-LLM baseline (H-det). It was written against the phrasing of the synthetic
    dev requests, so its accuracy on this synthetic set is optimistic; real requests would need the LLM extractor."""
    out = {}
    wanted = {"NDA": ["purpose"], "IMA": ["strategy", "mandate_size_sgd_m"], "DIST": ["fund_name"], "SIDE": ["commitment_usd_m"],
              "SUBS": ["subscription_amount_sgd_m", "fund_name"]}[agreement_type]
    for f in wanted:
        m = PATTERNS[f].search(text)
        if m:
            out[f] = normalise(f, m.group(1).strip())
    if agreement_type == "SIDE" and re.search(r"flagship fund", text, re.I):
        out["fund_name"] = "Flagship Fund"
    m = DATE_IN_TEXT.search(text)
    if m:
        out["_text_date"] = parse_date(m.group(1))
    return out
