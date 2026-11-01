"""Freeze the held-out TaxRAG question set (data/tax/questions_heldout.jsonl) from the audited drafts.

The drafts were written by five writer agents (one per topic area: group relief, carry-back, start of business,
renovation + deductions + capital allowances, general Act) and audited by five independent agents that checked
each evidence quote, gold completeness, wording leakage and out-of-scope claims (docs/taxrag-results.md,
"Question set"). This script applies the deterministic checks on top, then splits dev/test.

    python scripts/build_tax_questions.py <audited.json>

Checks (a question failing any is dropped, and the reason is reported):
  * the auditor did not drop it; its type is known; out-of-scope questions have no gold and the others do
  * every gold unit exists in the corpus; the evidence quote appears verbatim (whitespace aside) in the evidence
    chunk, and that chunk belongs to a gold unit (the teammate's tests/test_questions.py rule)
  * section_ref and old_number questions name an Act section (the teammate's detector); natural ones do not;
    an old_number question's number maps to its gold section
  * no run of 7 or more consecutive words copied from a gold chunk (leakage)
  * not a near duplicate (word-set Jaccard > 0.6) of another question or of the teammate's 28
Split: one third dev (all tuning), two thirds test (frozen), stratified by area and type, seeded.
Evidence quotes are IRAS text and stay out of this public repo: they go to .cache/tax/heldout_evidence.jsonl.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common import CACHE  # noqa: E402
from src.tax.corpus import QUESTION_SETS, chunks, load_tax_questions, tax_rag  # noqa: E402

TYPES = {"natural", "section_ref", "old_number", "out_of_scope"}
LEAK_WORDS = 7
DUP_JACCARD = 0.6
DEV_SHARE = 1 / 3
SEED = 3415


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def longest_copy(question: str, source: str) -> int:
    """Longest run of consecutive words of the question that also occurs in the source."""
    q, s = words(question), " " + " ".join(words(source)) + " "
    best = 0
    for i in range(len(q)):
        for j in range(i + best + 1, len(q) + 1):
            if " " + " ".join(q[i:j]) + " " in s:
                best = j - i
            else:
                break
    return best


def jaccard(a: str, b: str) -> float:
    x, y = set(words(a)), set(words(b))
    return len(x & y) / len(x | y) if x | y else 0.0


def main(path: Path) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    rag = tax_rag()
    rows = chunks("structured")
    by_id = {c.chunk_id: c for c in rows}
    sections = {c.section for c in rows if c.doc_type == "act"}
    paras = {(c.chunk_id.split(":", 1)[0], re.sub(r"#\d+$", "", c.chunk_id.split(":", 1)[1])) for c in rows if c.doc_type == "guide"}
    former = {c.former_section: c.section for c in rows if c.former_section}
    unit_text: dict[tuple[str, str], str] = defaultdict(str)
    for c in rows:
        unit = ("ITA", c.section) if c.doc_type == "act" else (c.chunk_id.split(":", 1)[0], re.sub(r"#\d+$", "", c.chunk_id.split(":", 1)[1]))
        unit_text[unit] += "\n" + c.text
    reference = [q.question for q in load_tax_questions("reference")]

    audited = json.loads(path.read_text(encoding="utf-8"))
    kept, dropped = [], defaultdict(list)
    for area in audited:
        for q in area["verified"]:
            q = dict(q, area=area["area"])
            reason = check(q, rag, by_id, sections, paras, former, unit_text)
            if not reason:
                dup = [r for r in reference if jaccard(q["question"], r) > DUP_JACCARD]
                dup += [k["question"] for k in kept if jaccard(q["question"], k["question"]) > DUP_JACCARD]
                reason = f"near duplicate of: {dup[0][:60]}" if dup else ""
            if reason:
                dropped[reason.split(":")[0]].append(f"{q['local_id']}: {reason}")
            else:
                kept.append(q)

    # stratified, seeded dev/test split
    rng = random.Random(SEED)
    strata = defaultdict(list)
    for q in kept:
        strata[(q["area"], q["type"])].append(q)
    for key in sorted(strata):
        group = sorted(strata[key], key=lambda q: hashlib.sha256(q["question"].encode()).hexdigest())
        rng.shuffle(group)
        n_dev = round(len(group) * DEV_SHARE)
        for i, q in enumerate(group):
            q["split"] = "dev" if i < n_dev else "test"
    kept.sort(key=lambda q: q["local_id"])
    out, evidence = [], []
    for i, q in enumerate(kept, start=1):
        qid = f"h{i:03d}"
        out.append(dict(id=qid, question=q["question"], gold_sections=q["gold_sections"], gold_paras=q["gold_paras"], evidence="",
                        type=q["type"], status="AUDITED", split=q["split"], area=q["area"], source_id=q["local_id"],
                        evidence_chunk_id=q["evidence_chunk_id"]))
        evidence.append(dict(id=qid, evidence=q["evidence"], evidence_chunk_id=q["evidence_chunk_id"]))
    target = QUESTION_SETS["heldout"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8")
    (CACHE / "tax").mkdir(parents=True, exist_ok=True)
    (CACHE / "tax" / "heldout_evidence.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in evidence), encoding="utf-8")
    report = {"kept": len(out), "by_split": {s: sum(r["split"] == s for r in out) for s in ("dev", "test")},
              "by_type": {t: sum(r["type"] == t for r in out) for t in sorted(TYPES)},
              "by_area": {a: sum(r["area"] == a for r in out) for a in sorted({r["area"] for r in out})},
              "dropped": {k: len(v) for k, v in dropped.items()}, "dropped_detail": dropped,
              "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
    (target.parent / "questions_heldout.report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "dropped_detail"}, indent=1))


def check(q, rag, by_id, sections, paras, former, unit_text) -> str:
    if q.get("verdict") == "drop":
        return f"auditor: {q.get('reason', '')[:80]}"
    if q["type"] not in TYPES:
        return f"type: {q['type']}"
    gold = {("ITA", s) for s in q["gold_sections"]} | {tuple(p.split(":", 1)) for p in q["gold_paras"]}
    if q["type"] == "out_of_scope":
        return "gold: out-of-scope question has gold" if gold else ""
    if not gold:
        return "gold: answerable question without gold"
    if len(gold) > 3:
        return "gold: more than 3 units"
    missing = [u for u in gold if (u[0] == "ITA" and u[1] not in sections) or (u[0] != "ITA" and u not in paras)]
    if missing:
        return f"gold: unknown unit {missing}"
    c = by_id.get(q["evidence_chunk_id"])
    if c is None:
        return f"evidence: unknown chunk {q['evidence_chunk_id']}"
    if squash(q["evidence"]) not in squash(c.text):
        return "evidence: quote not verbatim in its chunk"
    if not rag.evaluate.units_hit(c, gold, {}):
        return "evidence: chunk is not in a gold unit"
    refs = [r for r in rag.refs.find_section_refs(q["question"]) if not r.is_external]
    if q["type"] == "natural" and refs:
        return f"type: natural question names s {refs[0].canonical}"
    if q["type"] in ("section_ref", "old_number") and not refs:
        return "type: no section reference detected"
    if q["type"] == "old_number":
        golds = set(q["gold_sections"])
        if not any(former.get(r.section) in golds and r.section not in sections for r in refs):
            return "type: old number does not map to a gold section"
    leak = max(longest_copy(q["question"], unit_text[u]) for u in gold)
    if leak >= LEAK_WORDS:
        return f"leakage: {leak} consecutive words copied from a gold unit"
    return ""


if __name__ == "__main__":
    main(Path(sys.argv[1]))
