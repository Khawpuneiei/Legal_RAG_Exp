"""FastAPI application: staff request form, drafting workflow, Legal review, audit trail, scoreboard.

Run locally:   uvicorn src.app.main:app --reload
Vercel:        index.py re-exports `app`
Kubernetes:    gunicorn -k uvicorn.workers.UvicornWorker src.app.main:app (deploy/docker/Dockerfile)
"""
from __future__ import annotations

import csv
import json
import logging
import math
import time
import uuid
from collections import defaultdict, deque
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from src.agreement.library import load_library
from src.agreement.render import render_docx
from src.app import pii
from src.app.config import settings
from src.app.store import MemoryStore, StoreError, SupabaseStore

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
log = logging.getLogger("legal-agreement-ai")
logging.basicConfig(level=logging.INFO, format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":%(message)s}')

ROLES = {"requester": "Requester (staff)", "legal_reviewer": "Legal reviewer", "senior_legal": "Senior Legal / Compliance"}
SAMPLES = [("REQ-005", "Clean NDA"), ("REQ-006", "Clean IMA"), ("REQ-011", "NDA with a material deviation"), ("REQ-042", "Missing required field"),
           ("REQ-001", "Date conflict"), ("REQ-020", "Fee out of range"), ("REQ-009", "Unapproved governing law"), ("REQ-026", "Counterparty name mismatch"),
           ("REQ-013", "Clause the library does not have"), ("REQ-022", "Prompt injection in the request")]
LAW_OPTIONS = ["Singapore", "England and Wales", "New York", "Hong Kong"]

app = FastAPI(title="Legal Agreement AI", version="1.0.0",
              description="AI-assisted legal agreement drafting with human review, for a MAS-regulated fund manager (synthetic data only).",
              docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")


# --------------------------------------------------------------------------------------------- wiring
@lru_cache(maxsize=1)
def store():
    s = settings()
    if s.store == "supabase":
        return SupabaseStore(s.supabase_url, s.supabase_key)
    if s.store == "postgres":
        from src.app.store import PostgresStore
        return PostgresStore(s.database_url)
    return MemoryStore()


@lru_cache(maxsize=1)
def search():
    from src.app import search as sb
    s = settings()
    kind = s.search
    if kind == "auto":
        kind = "supabase" if s.store == "supabase" else ("postgres" if s.store == "postgres" and s.embed_url else "keyword")
    if kind == "supabase":
        return sb.SupabaseSearch(s.supabase_url, s.supabase_anon_jwt, s.supabase_key)
    if kind == "postgres":
        return sb.PostgresSearch(store(), s.embed_url)
    if kind == "local":
        return sb.LocalSearch()
    return sb.KeywordSearch()


@lru_cache(maxsize=1)
def llm():
    s = settings()
    from src.llm.ollama import OpenAICompatLLM
    if s.llm_base_url and s.llm_model:
        return OpenAICompatLLM(s.llm_base_url, s.llm_model)
    if s.ollama_host:
        return OpenAICompatLLM(s.ollama_host.rstrip("/") + "/v1", s.llm_model or "qwen2.5:7b", timeout=300)
    return None


def draft_for(agreement_type: str, form: dict, text: str) -> dict:
    from src.drafting.engine import make_draft
    mode = settings().effective_mode
    model = llm() if mode != "rules" else None
    if mode != "rules" and model is None:
        mode = "rules"
    return make_draft(agreement_type, form, text, search(), mode=mode, llm=model)


# --------------------------------------------------------------------------------------------- middleware
_hits: dict[str, deque] = defaultdict(deque)
# Prometheus metrics (per process; scraped per pod in Kubernetes). No client library needed for counters/histograms.
_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60)
_http_count: dict[tuple, int] = defaultdict(int)
_http_hist: dict[tuple, list] = defaultdict(lambda: [0] * (len(_BUCKETS) + 1))
_http_sum: dict[tuple, float] = defaultdict(float)
_drafts: dict[tuple, int] = defaultdict(int)


def _observe(method: str, route: str, status: int, seconds: float) -> None:
    _http_count[(method, route, status)] += 1
    key = (method, route)
    _http_sum[key] += seconds
    h = _http_hist[key]
    for i, b in enumerate(_BUCKETS):
        if seconds <= b:
            h[i] += 1
    h[-1] += 1


@app.middleware("http")
async def guard(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    t0 = time.time()
    if request.method == "POST":
        origin = request.headers.get("origin")
        if origin and request.url.netloc not in origin and request.url.path != "/api/v1/search":
            return JSONResponse({"detail": "cross-origin form posts are not allowed"}, status_code=403)
        ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
        q = _hits[ip]
        now = time.time()
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= settings().rate_limit_per_min:
            return JSONResponse({"detail": "rate limit exceeded, try again in a minute"}, status_code=429)
        q.append(now)
    try:
        response = await call_next(request)
    except Exception:  # noqa: BLE001
        log.exception(json.dumps(dict(event="unhandled", path=request.url.path, request_id=rid)))
        response = JSONResponse({"detail": "internal error", "request_id": rid}, status_code=500)
    response.headers.update({
        "X-Request-ID": rid, "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    })
    route = getattr(request.scope.get("route"), "path", "unmatched")
    _observe(request.method, route, response.status_code, time.time() - t0)
    if request.url.path.startswith("/api/") or request.method == "POST":
        log.info(json.dumps(dict(event="http", method=request.method, path=request.url.path, status=response.status_code,
                                 ms=round((time.time() - t0) * 1000), request_id=rid)))
    return response


def identity(request: Request) -> tuple[str, str]:
    role = request.cookies.get("role", "requester")
    role = role if role in ROLES else "requester"
    name = (request.cookies.get("name") or {"requester": "Demo Requester", "legal_reviewer": "Demo Legal Reviewer", "senior_legal": "Demo Senior Counsel"}[role])[:60]
    return role, name


def ctx(request: Request, **kw) -> dict:
    s = settings()
    role, name = identity(request)
    lib = load_library()
    return dict(request=request, role=role, name=name, roles=ROLES, demo=s.demo_mode, env=s.env, mode=s.effective_mode,
                store_name=store().name, search_name=getattr(search(), "name", "?"), policy_sha=lib.policy_sha256[:12],
                library_sha=lib.library_sha256[:12], **kw)


# --------------------------------------------------------------------------------------------- domain helpers
@lru_cache(maxsize=1)
def intake_items() -> dict:
    out = {}
    with open(ROOT / "data" / "synthetic" / "intake.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            out[r["request_id"]] = r
    return out


def form_spec(agreement_type: str) -> list[dict]:
    lib = load_library()
    req = lib.required_fields(agreement_type)
    if agreement_type == "SIDE":
        req = req + ["fee_rebate_bps"]
    out = []
    for f in req:
        kind = "date" if f.endswith("_date") else "number" if f in lib.policy["ranges"] or f.endswith("_pct") or f.endswith("_m") else "law" if f == "governing_law" else "text"
        out.append(dict(name=f, label=f.replace("_", " ").replace("pct", "(%)").replace("sgd m", "(S$ m)").replace("usd m", "(US$ m)").replace("bps", "(bps)").capitalize(),
                        kind=kind, required=f in lib.required_fields(agreement_type), range=lib.policy["ranges"].get(f)))
    return out


def all_form_specs() -> dict:
    return {t: form_spec(t) for t in load_library().types}


def create_request(agreement_type: str, form: dict, text: str, requester: str, role: str) -> dict:
    lib = load_library()
    if agreement_type not in lib.types:
        raise HTTPException(422, "unknown agreement type")
    clean_form = {k: v for k, v in form.items() if v not in (None, "")}
    masked, findings = pii.mask(text)
    payload = dict(requester=requester, role=role, agreement_type=agreement_type, form=clean_form, text_masked=masked, pii_findings=findings)
    if settings().processing == "inline":
        payload["draft"] = draft_for(agreement_type, clean_form, masked)
    try:
        res = store().submit(payload)
    except StoreError as e:
        raise HTTPException(400, str(e)) from e
    d = payload.get("draft") or {}
    _drafts[(agreement_type, d.get("mode", "queued"), d.get("route", "pending"))] += 1
    return res


def clause_view(cid: str) -> dict:
    c = load_library().clauses.get(cid)
    return dict(clause_id=cid, title=c["title"], text=c["text"], variant=c["variant"], version=c["version"], deviation_cost=c["deviation_cost"]) if c else dict(clause_id=cid, title="(not in library)", text="", variant="?", version="?", deviation_cost=0)


# --------------------------------------------------------------------------------------------- HTML pages
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    try:
        stats, recent, err = store().stats(), store().list(limit=8), None
    except Exception as e:  # noqa: BLE001
        stats, recent, err = {}, [], str(e)[:200]
    return templates.TemplateResponse(request, "index.html", ctx(request, stats=stats, recent=recent, store_error=err, samples=SAMPLES))


@app.get("/requests/new", response_class=HTMLResponse)
def new_request(request: Request, sample: str | None = None):
    pre = intake_items().get(sample) if sample else None
    return templates.TemplateResponse(request, "new_request.html", ctx(request, specs=all_form_specs(), samples=SAMPLES, pre=pre, laws=LAW_OPTIONS,
                                                                      types={t: load_library().title(t) for t in load_library().types}))


@app.post("/requests")
async def submit_form(request: Request):
    form = await request.form()
    role, name = identity(request)
    t = str(form.get("agreement_type") or "")
    text = str(form.get("text") or "")[:5000]
    spec = {f["name"]: f for f in form_spec(t)} if t in load_library().types else {}
    fields = {}
    for k, f in spec.items():
        v = str(form.get(f"{t}__{k}") or "").strip()
        if v:
            fields[k] = float(v) if f["kind"] == "number" and _num(v) else v
    res = create_request(t, fields, text, name, role)
    return RedirectResponse(f"/requests/{res['id']}", status_code=303)


def _num(v: str) -> bool:
    try:
        float(v)
        return True
    except ValueError:
        return False


@app.get("/requests/{rid}", response_class=HTMLResponse)
def request_page(request: Request, rid: str):
    data = store().get(rid)
    if not data:
        raise HTTPException(404, "request not found")
    d = data.get("draft") or {}
    order = (d.get("evidence") or {}).get("clause_order") or []
    sel_ids = {s.get("clause_id") for s in d.get("selections") or []}
    lib = load_library()
    std = set(lib.standard.get(data["request"]["agreement_type"], []))
    preview = [dict(clause_view(c), selected=c in sel_ids, added=c not in std and c not in sel_ids) for c in order]
    return templates.TemplateResponse(request, "request.html", ctx(request, data=data, r=data["request"], d=d, preview=preview,
                                                                  clause_view=clause_view, required=lib.required_fields(data["request"]["agreement_type"])))


@app.post("/requests/{rid}/review")
async def review_form(request: Request, rid: str):
    form = await request.form()
    role, name = identity(request)
    try:
        store().review(dict(request_id=rid, decision=str(form.get("decision")), comment=str(form.get("comment") or "")[:2000], reviewer=name, role=role))
    except StoreError as e:
        return RedirectResponse(f"/requests/{rid}?error={str(e)[:200]}", status_code=303)
    return RedirectResponse(f"/requests/{rid}", status_code=303)


@app.get("/requests/{rid}/draft.docx")
def draft_docx(rid: str):
    data = store().get(rid)
    if not data or not data.get("draft"):
        raise HTTPException(404, "no draft")
    r, d = data["request"], data["draft"]
    lib = load_library()
    blob, _ = render_docx(lib, r["agreement_type"], d["fields"], [s["clause_id"] for s in d["selections"] if s.get("clause_id")], d["issues"],
                          dict(request_id=r["ref"], config=f"{d.get('mode')} / {(d.get('config') or {}).get('search_backend')}", **(d.get("config") or {})))
    return Response(blob, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{r["ref"]}-draft.docx"'})


@app.get("/queue", response_class=HTMLResponse)
def queue(request: Request, status: str | None = None):
    rows = store().list(status=status or None, limit=100)
    return templates.TemplateResponse(request, "queue.html", ctx(request, rows=rows, status=status))


@app.get("/audit", response_class=HTMLResponse)
def audit_page(request: Request):
    return templates.TemplateResponse(request, "audit.html", ctx(request, events=store().audit(200), chain=store().verify_audit()))


@app.post("/role")
async def set_role(request: Request):
    form = await request.form()
    role = str(form.get("role") or "requester")
    resp = RedirectResponse(str(form.get("next") or "/"), status_code=303)
    if role in ROLES:
        resp.set_cookie("role", role, httponly=True, samesite="lax", secure=request.url.scheme == "https", max_age=86400)
        resp.delete_cookie("name")
    return resp


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _pivot(rows: list[dict] | None, metrics: list[str]) -> tuple[list[str], dict]:
    if not rows:
        return [], {}
    conds, table = [], defaultdict(dict)
    for r in rows:
        if r.get("condition") not in conds:
            conds.append(r["condition"])
        if r.get("metric") in metrics:
            table[r["condition"]][r["metric"]] = r
    return conds, table


def _fmt(cell, pct=True):
    if not cell or cell.get("mean") is None or (isinstance(cell.get("mean"), float) and math.isnan(cell["mean"])):
        return "–"
    m = cell["mean"]
    return f"{m:.2f}" if pct else f"{m:,.0f}"


@app.get("/scoreboard", response_class=HTMLResponse)
def scoreboard(request: Request):
    res = ROOT / "eval" / "results"
    e1m = ["success", "field_accuracy", "ask_recall", "hallucinated_clause_rate", "defect_recall", "false_alarm_on_clean", "route_correct", "checklist_compliance", "total_tokens"]
    e2m = ["success", "pass^3", "defect_recall", "false_alarm_on_clean", "route_correct", "escalation_precision", "escalation_recall", "ask_recall", "total_tokens", "latency_s"]
    exp1 = _pivot(_load_json(res / "exp1" / "summary.json"), e1m)
    exp2 = _pivot(_load_json(res / "exp2" / "summary.json"), e2m)
    exp3 = defaultdict(dict)
    try:
        with open(res / "exp3" / "summary.csv", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["metric"] in ("ndcg@10", "recall@5", "char_r@8kchars"):
                    exp3[(row["dataset"], row["metric"])][row["condition"]] = float(row["mean"])
    except OSError:
        pass
    gen = _pivot(_load_json(res / "exp3" / "generation_summary.json"), ["hallucinated_rate", "citation_accuracy", "ask_recall"])
    judge = (res / "judge" / "summary.md").read_text(encoding="utf-8") if (res / "judge" / "summary.md").exists() else None
    return templates.TemplateResponse(request, "scoreboard.html", ctx(request, exp1=exp1, e1m=e1m, exp2=exp2, e2m=e2m, exp3=exp3, gen=gen, fmt=_fmt, judge=judge))


@app.get("/results/{exp}/{name}")
def result_figure(exp: str, name: str):
    if exp not in ("exp1", "exp2", "exp3") or not name.endswith(".png") or "/" in name or ".." in name:
        raise HTTPException(404)
    p = ROOT / "eval" / "results" / exp / "figures" / name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/architecture", response_class=HTMLResponse)
def architecture(request: Request):
    return templates.TemplateResponse(request, "architecture.html", ctx(request))


@app.get("/governance", response_class=HTMLResponse)
def governance(request: Request):
    return templates.TemplateResponse(request, "governance.html", ctx(request, policy=load_library().policy))


@app.get("/seed/library.json", tags=["ops"])
def library_export():
    """The approved clause library (with contextual-retrieval prefixes and graph edges) for the search index sync job.
    Public: the library is synthetic. In production this endpoint is replaced by the SharePoint library sync."""
    lib = load_library()
    ctxs = {}
    with open(ROOT / "data" / "synthetic" / "clause_context.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            ctxs[r["clause_id"]] = r["context"]
    clauses = [dict(clause_id=c["clause_id"], version=c["version"], type=c["type"], title=c["title"], variant=c["variant"], templates=c["templates"],
                    deviation_cost=c["deviation_cost"], alternative_of=c["alternative_of"], body=c["text"], context=ctxs.get(c["clause_id"]))
               for c in lib.clauses.values()]
    return JSONResponse(dict(library_sha256=lib.library_sha256, clauses=clauses, edges=lib.edges), headers={"Cache-Control": "public, max-age=300"})


@app.get("/docs/figures/{name}")
def doc_figure(name: str):
    p = ROOT / "docs" / "figures" / name
    if not name.endswith((".png", ".svg")) or "/" in name or ".." in name or not p.exists():
        raise HTTPException(404)
    return FileResponse(p, headers={"Cache-Control": "public, max-age=3600"})


# --------------------------------------------------------------------------------------------- JSON API
class RequestIn(BaseModel):
    agreement_type: Literal["NDA", "IMA", "DIST", "SIDE", "SUBS"]
    form: dict = Field(default_factory=dict, description="Structured form fields (see the checklist for each agreement type)")
    text: str = Field(default="", max_length=5000, description="Free-text request; treated as data, never as instructions")
    requester: str = Field(default="api-client", max_length=80)


class ReviewIn(BaseModel):
    decision: Literal["approve", "reject", "request_changes", "escalate"]
    comment: str = Field(default="", max_length=2000)
    reviewer: str = Field(max_length=80)
    role: Literal["legal_reviewer", "senior_legal"]


class SearchIn(BaseModel):
    query: str = Field(max_length=1000)
    agreement_type: Literal["NDA", "IMA", "DIST", "SIDE", "SUBS"] | None = None
    k: int = Field(default=5, ge=1, le=20)


@app.post("/api/v1/requests", status_code=201, tags=["requests"])
def api_create(body: RequestIn):
    res = create_request(body.agreement_type, body.form, body.text, body.requester, "requester")
    return store().get(res["id"]) or res


@app.get("/api/v1/requests", tags=["requests"])
def api_list(status: str | None = None, limit: int = 50):
    return store().list(status=status, limit=min(max(limit, 1), 200))


@app.get("/api/v1/requests/{rid}", tags=["requests"])
def api_get(rid: str):
    data = store().get(rid)
    if not data:
        raise HTTPException(404, "request not found")
    return data


@app.post("/api/v1/requests/{rid}/review", tags=["review"])
def api_review(rid: str, body: ReviewIn):
    try:
        return store().review(dict(request_id=rid, **body.model_dump()))
    except StoreError as e:
        raise HTTPException(409, str(e)) from e


@app.get("/api/v1/audit", tags=["audit"])
def api_audit(limit: int = 100):
    return store().audit(min(max(limit, 1), 500))


@app.get("/api/v1/audit/verify", tags=["audit"])
def api_audit_verify():
    return store().verify_audit()


@app.post("/api/v1/search", tags=["search"])
def api_search(body: SearchIn):
    return search().search(body.query, k=body.k, agreement_type=body.agreement_type)


@app.post("/api/v1/draft/preview", tags=["requests"])
def api_preview(body: RequestIn):
    """Run the drafting engine without storing anything (for testing integrations)."""
    masked, findings = pii.mask(body.text)
    return dict(pii_findings=findings, draft=draft_for(body.agreement_type, body.form, masked))


@app.get("/api/v1/version", tags=["ops"])
def api_version():
    from src.drafting.engine import code_version
    s, lib = settings(), load_library()
    return dict(app=app.version, code=code_version(), env=s.env, store=store().name, search=getattr(search(), "name", "?"), drafting_mode=s.effective_mode,
                processing=s.processing, policy_sha256=lib.policy_sha256, library_sha256=lib.library_sha256, llm=getattr(llm(), "model", None))


@app.get("/metrics", include_in_schema=False)
def metrics():
    lines = ["# HELP http_requests_total HTTP requests by method, route template and status.", "# TYPE http_requests_total counter"]
    for (m, r, st), n in sorted(_http_count.items()):
        lines.append(f'http_requests_total{{method="{m}",route="{r}",status="{st}"}} {n}')
    lines += ["# HELP http_request_duration_seconds Request latency.", "# TYPE http_request_duration_seconds histogram"]
    for (m, r), h in sorted(_http_hist.items()):
        for b, c in zip(_BUCKETS, h):
            lines.append(f'http_request_duration_seconds_bucket{{method="{m}",route="{r}",le="{b}"}} {c}')
        lines.append(f'http_request_duration_seconds_bucket{{method="{m}",route="{r}",le="+Inf"}} {h[-1]}')
        lines.append(f'http_request_duration_seconds_sum{{method="{m}",route="{r}"}} {_http_sum[(m, r)]:.6f}')
        lines.append(f'http_request_duration_seconds_count{{method="{m}",route="{r}"}} {h[-1]}')
    lines += ["# HELP drafts_total Drafts produced by agreement type, drafting mode and route.", "# TYPE drafts_total counter"]
    for (t, mode, rt), n in sorted(_drafts.items()):
        lines.append(f'drafts_total{{agreement_type="{t}",mode="{mode}",route="{rt}"}} {n}')
    return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


@app.get("/healthz", tags=["ops"])
def healthz():
    return {"status": "ok"}


@app.get("/readyz", tags=["ops"])
def readyz():
    checks = {}
    for name, fn in (("store", lambda: store().ping()), ("search", lambda: search().ping())):
        try:
            checks[name] = bool(fn())
        except Exception as e:  # noqa: BLE001
            checks[name] = f"error: {type(e).__name__}"
    ok = all(v is True for v in checks.values())
    return JSONResponse(dict(status="ready" if ok else "degraded", checks=checks), status_code=200 if ok else 503)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/") or "text/html" not in request.headers.get("accept", ""):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return templates.TemplateResponse(request, "error.html", ctx(request, code=exc.status_code, detail=exc.detail), status_code=exc.status_code)
