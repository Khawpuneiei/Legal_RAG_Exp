"""Load SKILL.md skills (Anthropic Agent Skills layout) and build the skill variants of Experiment 1."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "skills"
MAIN = "legal-agreement-drafting"
MODULE_INDEX = {
    "checklists/nda.md": "Required fields, approved ranges and special-request clauses for NDAs",
    "checklists/ima.md": "Required fields, approved ranges and special-request clauses for investment management agreements",
    "checklists/dist.md": "Required fields, approved ranges and special-request clauses for distribution agreements",
    "checklists/side.md": "Required fields, approved ranges and special-request clauses for side letters",
    "checklists/subs.md": "Required fields, approved ranges and special-request clauses for subscription agreements",
    "reference/fallback_positions.md": "Approved fallback clauses, deviation costs, which ones escalate, clauses that require each other",
    "reference/key_terms_glossary.md": "Defined terms used in the clause library",
}


def read_skill(name: str = MAIN) -> dict:
    base = SKILLS / name
    raw = (base / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
    front, body = (yaml.safe_load(m.group(1)), m.group(2).strip()) if m else ({}, raw.strip())
    modules = {}
    for path in MODULE_INDEX:
        p = base / path
        if p.exists():
            modules[path] = p.read_text(encoding="utf-8").strip()
    return dict(name=front.get("name", name), description=front.get("description", ""), body=body, modules=modules)


def skill_block(name: str, body: str, modules: dict[str, str]) -> str:
    parts = [f'<skill name="{name}">\n{body}\n</skill>']
    for path, text in modules.items():
        parts.append(f'<skill_file path="{path}">\n{text}\n</skill_file>')
    return "\n\n".join(parts)


def comprehensive_text(skill: dict) -> str:
    """Everything in one document (used as S1 system prompt content and as the S3 comprehensive SKILL.md)."""
    parts = [skill["body"]]
    for path, text in skill["modules"].items():
        parts.append(f"\n\n---\n## Module: {path}\n\n{text}")
    return "".join(parts)


def focused_modules(skill: dict, agreement_type: str) -> dict[str, str]:
    """Static focused loading (Exp 2 harnesses): the type's checklist plus the fallback positions."""
    keep = [f"checklists/{agreement_type.lower()}.md", "reference/fallback_positions.md"]
    return {p: skill["modules"][p] for p in keep if p in skill["modules"]}


def index_text(skill: dict) -> str:
    lines = [f"Skill `{skill['name']}`: {skill['description']}", "", "Files in the skill (SKILL.md is always loaded):"]
    lines += [f"- {p}: {d}" for p, d in MODULE_INDEX.items()]
    return "\n".join(lines)
