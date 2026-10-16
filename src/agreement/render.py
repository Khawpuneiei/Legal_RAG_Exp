"""Deterministic .docx rendering of a draft (plan component 4, Field Populator; format-validity metric).

The template's standard clauses are kept in order. A selected fallback replaces the standard clause it is an
alternative of; selected optional clauses go into a "Special Terms" section; definitions needed by any clause are
included. Required fields that are missing are printed as a visible placeholder so a reviewer cannot miss them.
"""
from __future__ import annotations

import io
import re

from docx import Document
from docx.shared import Pt, RGBColor

from src.agreement.library import Library

PLACEHOLDER = "[TO BE CONFIRMED BY REQUESTER]"
LEFTOVER = re.compile(r"\{ref:|\{\{|\}\}|\[x\]")


def assemble(lib: Library, agreement_type: str, selected: list[str]) -> list[str]:
    """Ordered clause ids of the final agreement."""
    std = list(lib.standard[agreement_type])
    sel = [c for c in selected if c in lib.clauses and lib.is_allowed(agreement_type, c)]
    replaced = {lib.clauses[c]["alternative_of"]: c for c in sel if lib.clauses[c].get("alternative_of")}
    body = [replaced.get(c, c) for c in std]
    extras = [c for c in sel if c not in body]
    # legal requirements (REQUIRES edges) of everything in the draft
    for c in list(body + extras):
        for dep in sorted(lib.requires.get(c, set())):
            if dep in body or dep in extras:
                continue
            std_of_dep = lib.clauses[dep].get("alternative_of")
            if std_of_dep in body:  # the dependency is a fallback: it replaces its standard clause
                body[body.index(std_of_dep)] = dep
            else:
                extras.append(dep)
    # definitions used by operative clauses
    used_terms = {t for c in body + extras for t in lib.clauses[c].get("uses_terms", [])}
    defs = [c for c in body if lib.clauses[c]["variant"] == "definition"]
    defs += [t for t in sorted(used_terms) if t in lib.clauses and t not in defs]
    operative = [c for c in body if lib.clauses[c]["variant"] != "definition"]
    special = [c for c in extras if lib.clauses[c]["variant"] != "definition"]
    return defs + operative + special


def render_docx(lib: Library, agreement_type: str, fields: dict, selected: list[str], issues: list[dict], meta: dict) -> tuple[bytes, dict]:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)
    title = lib.title(agreement_type).upper()
    doc.add_heading(title, level=0)
    banner = doc.add_paragraph()
    run = banner.add_run("DRAFT FOR LEGAL REVIEW - NOT FOR EXECUTION. Generated from approved templates and clauses; "
                         "every clause below is cited by clause_id and version.")
    run.bold = True
    run.font.color.rgb = RGBColor(0xB0, 0x30, 0x30)
    missing = []
    doc.add_heading("Schedule", level=1)
    table = doc.add_table(rows=0, cols=2)
    table.style = "Light Grid Accent 1"
    for name in lib.required_fields(agreement_type) + [k for k in fields if k not in lib.required_fields(agreement_type) and not k.startswith("_")]:
        v = fields.get(name)
        if v is None:
            missing.append(name)
        row = table.add_row().cells
        row[0].text = name.replace("_", " ").capitalize()
        row[1].text = PLACEHOLDER if v is None else (f"{v:g}" if isinstance(v, float) else str(v))
    order = assemble(lib, agreement_type, selected)
    defs = [c for c in order if lib.clauses[c]["variant"] == "definition"]
    ops = [c for c in order if lib.clauses[c]["variant"] != "definition"]
    doc.add_heading("1. Definitions", level=1)
    for i, c in enumerate(defs, 1):
        doc.add_paragraph(f"1.{i} {lib.clauses[c]['text']}  [{c} {lib.clauses[c]['version']}]")
    for i, c in enumerate(ops, 2):
        cl = lib.clauses[c]
        doc.add_heading(f"{i}. {cl['title']}", level=2)
        doc.add_paragraph(f"{cl['text']}  [{c} {cl['version']}]")
    if issues:
        doc.add_heading("Open issues for the reviewer", level=1)
        for it in issues:
            doc.add_paragraph(f"{it.get('type')}: {it.get('detail', '')}", style="List Bullet")
    foot = doc.add_paragraph()
    foot.add_run(f"Policy {meta.get('policy_sha256', '')[:12]} | library {meta.get('library_sha256', '')[:12]} | "
                 f"request {meta.get('request_id', '')} | configuration {meta.get('config', '')}").italic = True
    buf = io.BytesIO()
    doc.save(buf)
    data = buf.getvalue()
    full_text = "\n".join(p.text for p in doc.paragraphs)
    check = dict(rendered=True, n_clauses=len(order), missing_fields=missing,
                 leftover_placeholders=bool(LEFTOVER.search(full_text)), bytes=len(data))
    return data, check
