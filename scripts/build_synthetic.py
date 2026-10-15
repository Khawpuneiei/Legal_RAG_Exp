"""Build the synthetic clause library, rendered template documents, clause graph and requests.

Outputs (committed to git, deterministic for a given seed):
  data/synthetic/clauses.jsonl    one row per clause (clause_id, type, title, text, variant, ...)
  data/synthetic/documents.jsonl  rendered documents with exact character spans per clause
  data/synthetic/edges.jsonl      clause graph edges (CONTAINS, DEFINED_IN, REFERS_TO, REQUIRES, ALTERNATIVE_OF)
  data/synthetic/requests.jsonl   staff requests with graded gold clause ids (3 exact, 2 alternative, 1 same type)

Usage:  python scripts/build_synthetic.py [--seed 13] [--n 120]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import clause_catalog as cat  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "synthetic"
VERSION = "v1"
REF_RE = re.compile(r"\{ref:([A-Z0-9_]+)\}")


def all_operative() -> dict[str, dict]:
    clauses: dict[str, dict] = {}
    for group in (cat.BOILERPLATE, cat.NDA, cat.IMA, cat.DIST, cat.SIDE, cat.SUBS):
        for key, spec in group.items():
            assert key not in clauses, key
            clauses[key] = dict(spec)
    return clauses


def clause_id(key: str) -> str:
    return key.replace("_", "-") if not key.startswith("DEF:") else "DEF-" + key[4:].replace("_", "-")


def owner_template(key: str) -> str | None:
    for t, spec in cat.TEMPLATES.items():
        if key in spec["clauses"] or key in spec["pool"]:
            if not key.startswith("BP_"):
                return t
    return None


def build_library():
    operative = all_operative()
    # Numbering: definitions are 1.1..1.n, operative clauses 2..N in template order.
    numbering: dict[str, dict[str, str]] = {}
    for t, spec in cat.TEMPLATES.items():
        num = {}
        for i, d in enumerate(spec["definitions"], 1):
            num["DEF:" + d] = f"1.{i}"
        for i, c in enumerate(spec["clauses"], 2):
            num[c] = str(i)
        # pool clauses are numbered as Schedule items S1..Sn so references still resolve
        for i, c in enumerate(spec["pool"], 1):
            num.setdefault(c, f"S{i}")
        numbering[t] = num
    bp_num = {c: f"B{i}" for i, c in enumerate(cat.BP_POOL, 1)}

    def title_of(key: str) -> str:
        if key.startswith("DEF:"):
            return f'Definition of "{cat.DEFINITIONS[key[4:]][0]}"'
        return operative[key]["title"]

    def render_refs(text: str, template: str | None) -> tuple[str, list[str]]:
        refs = []

        def sub(m):
            target = m.group(1)
            if target == "FEE_CLAUSE":
                target = cat.FEE_CLAUSE.get(template or "", "IMA_MGMT_FEE")
            refs.append(target)
            num = numbering.get(template or "", {}).get(target) or bp_num.get(target) or "[x]"
            return f"Clause {num} ({title_of(target)})"

        return REF_RE.sub(sub, text), refs

    clauses: list[dict] = []
    # Definitions: one clause per term. MANAGEMENT_FEE's text references a template-specific clause,
    # so it is rendered per template that uses it (same clause_id, template-specific reference).
    term_names = {k: v[0] for k, v in cat.DEFINITIONS.items()}
    for key, (term, body) in cat.DEFINITIONS.items():
        templates = [t for t, s in cat.TEMPLATES.items() if key in s["definitions"]]
        text, refs = render_refs(f'"{term}" {body}', templates[0] if templates else None)
        clauses.append(dict(clause_id=clause_id("DEF:" + key), key="DEF:" + key, type="definition", title=f'Definition of "{term}"',
                            text=text, variant="definition", version=VERSION, templates=templates, defines=term,
                            alternative_of=None, deviation_cost=0.0, refers_to=[clause_id(r) for r in refs]))
    for key, spec in operative.items():
        owner = owner_template(key)
        templates = sorted({t for t, s in cat.TEMPLATES.items() if key in s["clauses"] or key in s["pool"]})
        text, refs = render_refs(spec["text"], owner)
        clauses.append(dict(clause_id=clause_id(key), key=key, type=spec["type"], title=spec["title"], text=text,
                            variant=spec["variant"], version=VERSION, templates=templates or ["ALL"], defines=None,
                            alternative_of=clause_id(spec["alternative_of"]) if spec.get("alternative_of") else None,
                            deviation_cost=spec.get("deviation_cost", 0.0), refers_to=[clause_id(r) for r in refs]))
    by_key = {c["key"]: c for c in clauses}

    # uses_terms: defined terms appearing in each clause's text (whole-word, case-sensitive)
    for c in clauses:
        used = []
        for k, term in term_names.items():
            if c["defines"] == term:
                continue
            if re.search(r"(?<![A-Za-z])" + re.escape(term) + r"(?![A-Za-z])", c["text"]):
                used.append(clause_id("DEF:" + k))
        c["uses_terms"] = used

    # Rendered documents with exact spans
    documents = []

    def render_doc(doc_id: str, title: str, items: list[tuple[str, str]], template: str | None) -> dict:
        parts, spans, pos = [], [], 0
        header = f"{title.upper()}\n\n"
        parts.append(header)
        pos += len(header)
        for num, key in items:
            c = by_key[key]
            heading = f"{num} {c['title']}\n" if not key.startswith("DEF:") else f"{num} "
            body = c["text"]
            if key.startswith("DEF:") and key[4:] == "MANAGEMENT_FEE" and template:
                body, _ = render_refs(f'"{cat.DEFINITIONS["MANAGEMENT_FEE"][0]}" {cat.DEFINITIONS["MANAGEMENT_FEE"][1]}', template)
            parts.append(heading)
            pos += len(heading)
            spans.append(dict(clause_id=c["clause_id"], start=pos, end=pos + len(body)))
            parts.append(body + "\n\n")
            pos += len(body) + 2
        return dict(doc_id=doc_id, title=title, template=template, text="".join(parts), spans=spans)

    for t, spec in cat.TEMPLATES.items():
        num = numbering[t]
        items = [(num["DEF:" + d], "DEF:" + d) for d in spec["definitions"]]
        items = [("1. DEFINITIONS\n" + items[0][0], items[0][1])] + items[1:]
        items += [(num[c] + ".", c) for c in spec["clauses"]]
        documents.append(render_doc(f"TEMPLATE-{t}", f"{spec['title']} (Template {t} {VERSION})", items, t))
        pool_items = [(num[c] + ".", c) for c in spec["pool"]]
        documents.append(render_doc(f"FALLBACKS-{t}", f"{spec['title']} - Fallback and Optional Clauses ({VERSION})", pool_items, t))
    documents.append(render_doc("FALLBACKS-BP", f"Boilerplate Fallback and Optional Clauses ({VERSION})",
                                [(bp_num[c] + ".", c) for c in cat.BP_POOL], None))

    # Sanity: every span's text equals the clause text (except per-template MANAGEMENT_FEE rendering)
    text_by_id = {c["clause_id"]: c["text"] for c in clauses}
    for d in documents:
        for s in d["spans"]:
            if s["clause_id"] != "DEF-MANAGEMENT-FEE":
                assert d["text"][s["start"]:s["end"]] == text_by_id[s["clause_id"]], (d["doc_id"], s)

    # Graph edges
    edges = []
    for t, spec in cat.TEMPLATES.items():
        for key in [*("DEF:" + d for d in spec["definitions"]), *spec["clauses"], *spec["pool"]]:
            edges.append(dict(src=f"TEMPLATE-{t}", dst=by_key[key]["clause_id"], type="CONTAINS", weight=0.1))
    for c in clauses:
        for d in c["uses_terms"]:
            edges.append(dict(src=c["clause_id"], dst=d, type="DEFINED_IN", weight=0.2))
        for r in c["refers_to"]:
            edges.append(dict(src=c["clause_id"], dst=r, type="REFERS_TO", weight=0.3))
        if c["alternative_of"]:
            edges.append(dict(src=c["alternative_of"], dst=c["clause_id"], type="ALTERNATIVE_OF", weight=c["deviation_cost"]))
            edges.append(dict(src=c["clause_id"], dst=c["alternative_of"], type="ALTERNATIVE_OF", weight=c["deviation_cost"]))
    for a, b in cat.REQUIRES:
        edges.append(dict(src=clause_id(a), dst=clause_id(b), type="REQUIRES", weight=0.3))
    ids = set(text_by_id)
    for e in edges:
        assert e["dst"] in ids and (e["src"] in ids or e["src"].startswith("TEMPLATE-")), e
    return clauses, documents, edges, by_key


COUNTERPARTIES = {
    "NDA": [("Harbourfront Capital Pte. Ltd.", "a family office"), ("Lion City Wealth Partners", "an independent wealth manager"), ("Marina Bay Securities Ltd", "a broker"),
            ("Kestrel Asia Holdings", "a strategic investor"), ("Tanjong Analytics Pte. Ltd.", "a data vendor"), ("Raffles Pension Trustees", "a pension consultant")],
    "IMA": [("Orchard Family Office Pte. Ltd.", "single-family office"), ("Straits Insurance Berhad", "insurer"), ("Temasek Road Endowment", "university endowment"),
            ("Bukit Timah Holdings", "corporate treasury"), ("Pacific Crest Foundation", "charitable foundation")],
    "DIST": [("Merlion Private Bank", "private bank"), ("KL Capital Distributors Sdn Bhd", "Malaysian placement agent"), ("Jade Advisory Ltd", "Hong Kong introducer"),
             ("Sentosa Wealth Platform Pte. Ltd.", "digital wealth platform")],
    "SIDE": [("Nordic Public Pension Fund", "pension fund"), ("Gulf Sovereign Investment Authority", "sovereign wealth fund"), ("Sakura Life Insurance Co.", "insurer"),
             ("Evergreen University Endowment", "endowment"), ("Atlas Fund of Funds", "fund of funds")],
    "SUBS": [("Mr Tan Wei Ming", "individual accredited investor"), ("Clementi Holdings Pte. Ltd.", "investment holding company"), ("Central Provident Staff Pension", "statutory pension board"),
             ("Changi Reinsurance Ltd", "reinsurer")],
}
OPENERS = ["Hi Legal,", "Hello team,", "Dear Legal,", "Hi,", "Morning,"]
CLOSERS = ["Thanks!", "Many thanks.", "Appreciate it.", "Thanks in advance.", "Cheers."]
NAMES = ["Priya (Sales)", "Daniel (Ops)", "Mei Ling (IR)", "Arjun (Distribution)", "Sarah (PM team)", "Kenji (Product)"]


def body_for(t: str, cp: str, cp_type: str, rng: random.Random) -> tuple[str, dict]:
    if t == "NDA":
        purpose = rng.choice(["a possible fund distribution arrangement", "a potential seed investment in our new fund", "sharing data for a mandate pitch", "a joint product discussion"])
        return f"Could you prepare an NDA with {cp} ({cp_type})? We are discussing {purpose}.", dict(purpose=purpose)
    if t == "IMA":
        aum = rng.choice([30, 60, 120, 250])
        strategy = rng.choice(["Asian equities", "SGD fixed income", "multi-asset income", "Asia credit"])
        return f"We won a discretionary {strategy} mandate from {cp}, a {cp_type}, roughly S${aum}m. Please draft the IMA.", dict(aum_sgd_m=aum, strategy=strategy)
    if t == "DIST":
        fund = rng.choice(["Asia Income Fund", "Pan-Asia Equity VCC", "Asian Credit Opportunities Fund"])
        return f"{cp} ({cp_type}) wants to distribute our {fund}. Can we get a distribution agreement going?", dict(fund=fund)
    if t == "SIDE":
        amt = rng.choice([25, 50, 100, 200])
        return f"{cp}, a {cp_type}, is committing US${amt}m to the flagship fund and needs a side letter.", dict(commitment_usd_m=amt)
    amt = rng.choice([0.5, 1, 5, 20])
    return f"New subscription from {cp} ({cp_type}) for about S${amt}m into the Asia Income Fund. Please prepare the subscription agreement.", dict(subscription_sgd_m=amt)


def build_requests(by_key: dict, clauses: list[dict], n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    types_of = {c["clause_id"]: c["type"] for c in clauses}
    same_type: dict[str, list[str]] = {}
    for c in clauses:
        same_type.setdefault(c["type"], []).append(c["clause_id"])
    mix = ["NDA"] * 30 + ["IMA"] * 30 + ["DIST"] * 20 + ["SIDE"] * 25 + ["SUBS"] * 15
    rng.shuffle(mix)
    requests = []
    for i in range(n):
        t = mix[i % len(mix)]
        cp, cp_type = rng.choice(COUNTERPARTIES[t])
        body, fields = body_for(t, cp, cp_type, rng)
        applicable = [k for k, a in cat.ASKS.items() if t in a["templates"]]
        k = rng.choice([1, 1, 2, 2, 3])
        asks = rng.sample(applicable, min(k, len(applicable)))
        # avoid contradictory pairs
        if "non_solicit" in asks and "non_solicit_short" in asks:
            asks.remove("non_solicit_short")
        if "mfn" in asks and "mfn_limited" in asks:
            asks.remove("mfn_limited")
        if "english_law" in asks and "courts" in asks:
            asks.remove("courts")
        missing = []
        if rng.random() < 0.12:
            missing = [rng.choice(list(cat.MISSING_ASKS))]
            if rng.random() < 0.3:
                asks = []  # request consisting only of an unsupported ask
        lines = [rng.choice(cat.ASKS[a]["phrasings"]) for a in asks] + [rng.choice(cat.MISSING_ASKS[m]) for m in missing]
        rng.shuffle(lines)
        text = " ".join([rng.choice(OPENERS), body, *lines, rng.choice(CLOSERS), rng.choice(NAMES)])
        gold: dict[str, int] = {}
        for a in asks:
            g = cat.ASKS[a]["gold"]
            for key, grade in (g.get(t) or g.get("*")).items():
                cid = by_key[key]["clause_id"]
                gold[cid] = max(gold.get(cid, 0), grade)
        for cid in list(gold):
            if gold[cid] == 3:
                for other in same_type[types_of[cid]]:
                    gold.setdefault(other, 1)
        requests.append(dict(request_id=f"REQ-{i + 1:03d}", split="dev" if i < 30 else "test", agreement_type=t,
                             counterparty=cp, counterparty_type=cp_type, text=text, asks=asks, missing_asks=missing,
                             gold=gold, fields=fields))
    return requests


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--n", type=int, default=120)
    args = ap.parse_args()
    clauses, documents, edges, by_key = build_library()
    requests = build_requests(by_key, clauses, args.n, args.seed)
    write_jsonl(OUT / "clauses.jsonl", clauses)
    write_jsonl(OUT / "documents.jsonl", documents)
    write_jsonl(OUT / "edges.jsonl", edges)
    write_jsonl(OUT / "requests.jsonl", requests)
    n_with_gold = sum(1 for r in requests if any(g >= 2 for g in r["gold"].values()))
    print(f"clauses={len(clauses)} documents={len(documents)} edges={len(edges)} requests={len(requests)} "
          f"(with gold={n_with_gold}, with missing asks={sum(1 for r in requests if r['missing_asks'])})")
    by_type = {}
    for c in clauses:
        by_type[c["variant"]] = by_type.get(c["variant"], 0) + 1
    print("variants:", by_type)


if __name__ == "__main__":
    main()
