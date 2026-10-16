"""Production drafting engine: one entry point used by the API, the queue worker and the demo.

Modes (chosen from the Experiment 2 results, docs/architecture.md):
  rules   no LLM: rule segmentation of the request + A* clause assembly + Validation Engine + routing policy (H-det)
  assist  LLM extracts the special requests, then the same A* assembly and rules (H3b)
  agent   ReAct agent with tools + validation/reflection loop, rules own structural issues (H3)

Every mode returns the same draft dict, ready for api_submit / worker_complete, including the evidence a reviewer needs
(candidates per request, clause dependencies) and the configuration hashes written to the audit trail.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from src.agreement.library import Library, load_library
from src.agreement.render import assemble
from src.agreement.validation import check_request, check_selections, merge_issues, route as policy_route
from src.drafting.assembly import astar_assign, rule_requirements

ROOT = Path(__file__).resolve().parents[2]


def code_version() -> str:
    v = os.environ.get("VERCEL_GIT_COMMIT_SHA") or os.environ.get("GIT_SHA")
    if v:
        return v[:12]
    try:
        return subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=5).stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def prompt_hash() -> str:
    """Hash of everything that shapes LLM behaviour (skill files + harness prompts)."""
    h = hashlib.sha256()
    for p in sorted((ROOT / "skills" / "legal-agreement-drafting").rglob("*.md")):
        h.update(p.read_bytes())
    h.update((ROOT / "src" / "drafting" / "harness.py").read_bytes())
    return h.hexdigest()[:16]


class _Ctx:
    """Adapter so the experiment harness code runs unchanged in production."""

    def __init__(self, lib, search, llm, tau):
        self.lib, self.search, self.llm, self.seed, self.temperature, self.small_llm, self.tau = lib, search, llm, 0, 0.0, None, tau


def make_draft(agreement_type: str, form: dict, text: str, search, mode: str = "rules", llm=None, tau: float | None = None,
               lib: Library | None = None) -> dict:
    lib = lib or load_library()
    tau = tau if tau is not None else getattr(search, "tau", 0.7)
    item = dict(request_id="live", agreement_type=agreement_type, form={"agreement_type": agreement_type, **form}, text=text)
    t = agreement_type
    evidence: dict = {"requirements": []}
    if mode == "agent":
        if llm is None:
            raise ValueError("agent mode needs an LLM")
        from src.drafting.harness import run_h3_core
        final, draft, tr, extra = run_h3_core(item, _Ctx(lib, search, llm, {}))
        fields, selections, issues, route_ = final["fields"], final["selections"], final["issues"], final["route"]
        note = final.get("reviewer_note") or ""
        evidence["llm_calls"] = tr.summary()["n_calls"]
        evidence["reflection_rounds"] = extra.get("reflection_rounds")
    else:
        if mode == "assist":
            if llm is None:
                raise ValueError("assist mode needs an LLM")
            from src.drafting.harness import Trace, extract_requirements
            ctx = _Ctx(lib, search, llm, {})
            reqs = extract_requirements(ctx, item, Trace(ctx))
        else:
            reqs = [dict(requirement=s, query=s) for s in rule_requirements(text)]
        # definitions are never a special request: keep operative clauses only
        cands = [[h for h in search.search(r["query"], k=8, agreement_type=t) if h.get("variant") != "definition"][:5] for r in reqs]
        assign, expanded = astar_assign(lib, cands, tau)
        selections = [dict(requirement=r["requirement"], clause_id=c) for r, c in zip(reqs, assign)]
        from src.drafting.harness import form_fields
        fields = form_fields(lib, item)
        issues = merge_issues(check_request(lib, t, item["form"], text),
                              [dict(type="unsupported_clause", field=None, detail=f"No approved clause found for: {s['requirement']}", source="astar")
                               for s in selections if s["clause_id"] is None])
        _, sel = check_selections(lib, t, [c for c in assign if c])
        route_ = policy_route(lib, issues, bool(sel["material"]))
        evidence["nodes_expanded"] = expanded
        evidence["requirements"] = [dict(requirement=r["requirement"], chosen=c,
                                         candidates=[dict(clause_id=h["clause_id"], title=h["title"], relevance=round(float(h.get("relevance", 0)), 3),
                                                          deviation_cost=h["deviation_cost"]) for h in cs])
                                    for r, c, cs in zip(reqs, assign, cands)]
        from src.drafting.harness import deterministic_note
        note = deterministic_note(lib, t, fields, selections, issues, route_)
    chosen = [s["clause_id"] for s in selections if s.get("clause_id")]
    _, sel = check_selections(lib, t, chosen)
    order = assemble(lib, t, sel["valid"])
    added = [c for c in order if c not in lib.standard[t] and c not in sel["valid"]]
    evidence["dependencies_added"] = added
    evidence["material_deviations"] = sel["material"]
    evidence["clause_order"] = order
    config = dict(policy_sha256=lib.policy_sha256, library_sha256=lib.library_sha256, code=code_version(), mode=mode,
                  search_backend=getattr(search, "name", type(search).__name__), tau=tau,
                  model=getattr(llm, "model", None) if llm is not None and mode != "rules" else None,
                  prompt_hash=prompt_hash() if mode != "rules" else None)
    return dict(mode=mode, config=config, fields={k: v for k, v in fields.items() if not str(k).startswith("_")}, selections=selections,
                issues=[{k: v for k, v in i.items()} for i in issues], route=route_, evidence=evidence, reviewer_note=note)


def draft_json(d: dict) -> str:
    return json.dumps(d, ensure_ascii=False, default=str)
