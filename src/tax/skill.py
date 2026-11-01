"""The tax-answering skill (skills/tax-answering, Anthropic Agent Skills layout) and the RQ1 variants built from it.

Same shapes as the legal skill (src/drafting/skills.py), so S1-S4 place the skill as in Experiment 1. The module
index is read from SKILL.md's "## Modules" list (``- `modules/x.md`: what it covers``) instead of a constant, and
the S2 routing reply is matched in the model's order with empty names ignored (the legal loader's `endswith("")`
matched every file).
"""
from __future__ import annotations

import re

import yaml

from src.common import ROOT

SKILLS = ROOT / "skills"
TAX_SKILL = "tax-answering"
SELF_SKILL = "tax-answering-self"   # S4: written by the answer model itself
MODULE_LINE = re.compile(r"^- `([^`]+\.md)`: (.+)$", re.M)
MAX_MODULES = 2
LOADED = "The following skill is loaded."


def read_skill(name: str = TAX_SKILL) -> dict:
    base = SKILLS / name
    raw = (base / "SKILL.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
    front, body = (yaml.safe_load(m.group(1)) or {}, m.group(2).strip()) if m else ({}, raw.strip())
    index = {path: desc.strip() for path, desc in MODULE_LINE.findall(body) if (base / path).exists()}
    modules = {path: (base / path).read_text(encoding="utf-8").replace("\r\n", "\n").strip() for path in index}
    return dict(name=front.get("name", name), description=front.get("description", ""), body=body, index=index, modules=modules)


def skill_block(name: str, body: str, modules: dict[str, str]) -> str:
    parts = [f'<skill name="{name}">\n{body}\n</skill>']
    for path, text in modules.items():
        parts.append(f'<skill_file path="{path}">\n{text}\n</skill_file>')
    return "\n\n".join(parts)


def comprehensive_text(skill: dict) -> str:
    """SKILL.md and every module in one document (S1's system-prompt text, S3's comprehensive skill)."""
    parts = [skill["body"]]
    for path, text in skill["modules"].items():
        parts.append(f"\n\n---\n## Module: {path}\n\n{text}")
    return "".join(parts)


def index_text(skill: dict) -> str:
    lines = [f"Skill `{skill['name']}`: {skill['description']}", "", "Files in the skill (SKILL.md is always loaded):"]
    lines += [f"- {p}: {d}" for p, d in skill["index"].items()]
    return "\n".join(lines)


def route_prompt(skill: dict, question: str) -> str:
    return (f"{index_text(skill)}\n\nQuestion: {question.strip()}\n\nWhich skill files do you need to load to answer this "
            f'question? Return JSON {{"load": ["<file path>", ...]}} with at most {MAX_MODULES} files.')


def chosen_modules(skill: dict, reply: dict, limit: int = MAX_MODULES) -> list[str]:
    """The index paths the routing reply names, in its order: an exact path or a file name, no empty names."""
    wanted = reply.get("load", []) if isinstance(reply, dict) else []
    out = []
    for w in wanted if isinstance(wanted, list) else []:
        w = w.strip() if isinstance(w, str) else ""
        name = w.split("/")[-1]
        if not name:
            continue
        match = next((p for p in skill["index"] if p == w or p.split("/")[-1] == name), None)
        if match and match not in out:
            out.append(match)
        if len(out) == limit:
            break
    return out
