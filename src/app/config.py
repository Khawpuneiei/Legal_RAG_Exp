"""Twelve-factor settings: everything comes from environment variables (no secrets in the repo)."""
from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass, field


_DEFAULTS: dict[str, str] = {}
if os.environ.get("VERCEL") == "1":  # free-tier demo: public defaults from configs/deployments/vercel.env
    _f = Path(__file__).resolve().parents[2] / "configs" / "deployments" / "vercel.env"
    if _f.exists():
        for _line in _f.read_text(encoding="utf-8").splitlines():
            if _line.strip() and not _line.lstrip().startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _DEFAULTS[_k.strip()] = _v.strip()


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, _DEFAULTS.get(name, default)).strip()


@dataclass(frozen=True)
class Settings:
    env: str = field(default_factory=lambda: _env("APP_ENV", "local"))                    # local | demo | staging | production
    store: str = field(default_factory=lambda: _env("STORE", "memory"))                   # memory | supabase | postgres
    search: str = field(default_factory=lambda: _env("SEARCH", "auto"))                   # auto | supabase | local | postgres
    processing: str = field(default_factory=lambda: _env("PROCESSING", "inline"))         # inline | queue
    drafting_mode: str = field(default_factory=lambda: _env("DRAFTING_MODE", "auto"))     # auto | rules | assist | agent
    supabase_url: str = field(default_factory=lambda: _env("SUPABASE_URL"))
    supabase_key: str = field(default_factory=lambda: _env("SUPABASE_PUBLISHABLE_KEY"))   # public by design; RLS + api_* functions guard data
    supabase_anon_jwt: str = field(default_factory=lambda: _env("SUPABASE_ANON_JWT"))     # public legacy anon key, for Edge Function JWT check
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL"))               # postgres store (Kubernetes); from a Secret
    embed_url: str = field(default_factory=lambda: _env("EMBED_URL"))                     # TEI-compatible /embed endpoint (gte-small)
    llm_base_url: str = field(default_factory=lambda: _env("LLM_BASE_URL"))               # OpenAI-compatible (LiteLLM, Azure, Groq, vLLM...)
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL"))
    ollama_host: str = field(default_factory=lambda: _env("OLLAMA_HOST"))
    demo_mode: bool = field(default_factory=lambda: _env("DEMO_MODE", "true").lower() == "true")
    rate_limit_per_min: int = field(default_factory=lambda: int(_env("RATE_LIMIT_PER_MIN", "20") or 20))

    @property
    def llm_configured(self) -> bool:
        return bool((self.llm_base_url and self.llm_model) or self.ollama_host)

    @property
    def effective_mode(self) -> str:
        if self.drafting_mode != "auto":
            return self.drafting_mode
        return "assist" if self.llm_configured else "rules"


def settings() -> Settings:
    return Settings()
