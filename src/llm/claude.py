"""Claude through the Anthropic API, behind the teammate's ChatModel protocol (rag.llm: `name`, `complete(system, user)`).

Every reply is cached on disk with its stop reason, the model that served it and its token usage, so a rerun spends
nothing on what it already has and a run's cost can be added up afterwards (`cost`). Credentials come from the
environment (ANTHROPIC_API_KEY; eval/tax_experiment.load_keys reads both .env files).

Claude Opus 5.5 always thinks before it answers; `effort` sets how much (its default is "medium", set explicitly here),
and `max_tokens` covers the thinking and the answer. A request a safety classifier declines is re-run server-side on
Anthropic's recommended fallback model (`fallbacks: "default"`); the cached record says which model answered.
"""
from __future__ import annotations

import threading

import anthropic

from src.common import JsonCache, stable_hash

MODEL = "claude-opus-5-5"
EFFORT = "medium"
MAX_TOKENS = 16000
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5")   # the models that take `fallbacks: "default"`
# USD per million tokens (list prices, October 2026): input, output, cache write (1.25x input), cache read. Output
# includes thinking. The runs here send no cache_control, so the cache columns stay at 0.
PRICES = {"claude-opus-5-5": (4.00, 20.00, 5.00, 0.20), "claude-sonnet-5-5": (2.00, 10.00, 2.50, 0.20),
          "claude-haiku-5-5": (0.10, 0.50, 0.125, 0.01),
          "claude-opus-5": (5.00, 25.00, 6.25, 0.50), "claude-opus-4-8": (5.00, 25.00, 6.25, 0.50)}   # fallback targets
_LOCK = threading.Lock()


class ClaudeChat:
    def __init__(self, model: str = MODEL, effort: str = EFFORT, max_tokens: int = MAX_TOKENS, client=None,
                 cache_name: str = "claude"):
        self.model, self.effort, self.max_tokens = model, effort, max_tokens
        self.client = client or anthropic.Anthropic(max_retries=5)
        self.name = f"claude:{model}" if effort == EFFORT else f"claude:{model}@{effort}"
        self.cache = JsonCache(f"{cache_name}-{model}")

    def key(self, system: str, user: str) -> str:
        return stable_hash(self.model, self.effort, str(self.max_tokens), system, user)

    def complete(self, system: str, user: str) -> str:
        return self.generate(system, user)["text"]

    def generate(self, system: str, user: str) -> dict:
        """{"text", "stop_reason", "served_by", "fallback", "usage", "cached"}. A refusal is an empty text."""
        key = self.key(system, user)
        hit = self.cache.get(key)
        if hit is not None:
            return {**hit, "cached": True}
        request = dict(model=self.model, max_tokens=self.max_tokens, system=system,
                       messages=[{"role": "user", "content": user}], output_config={"effort": self.effort})
        if self.model in FALLBACK_MODELS:
            request.update(betas=[FALLBACK_BETA], fallbacks="default")
        response = self.client.beta.messages.create(**request)
        refused = response.stop_reason == "refusal"
        text = "" if refused else "".join(b.text for b in response.content if b.type == "text")
        u = response.usage
        out = {"text": text, "stop_reason": response.stop_reason, "served_by": response.model,
               "fallback": any(b.type == "fallback" for b in response.content),
               "refusal_category": getattr(response.stop_details, "category", None) if refused else None,
               "usage": _tokens(u)}
        if any(it.type == "fallback_message" for it in u.iterations or []):   # each attempt is billed at its own model's rates
            out["iterations"] = [{"model": it.model or self.model, **_tokens(it)} for it in u.iterations]
        with _LOCK:
            self.cache.put(key, out)
        return {**out, "cached": False}


def _tokens(u) -> dict:
    return {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
            "cache_creation_input_tokens": u.cache_creation_input_tokens or 0, "cache_read_input_tokens": u.cache_read_input_tokens or 0}


def cost(records: list[dict]) -> float:
    """USD for these generate() records at list prices: each attempt of a fallback at its own model's rates, any other
    reply at the rates of the model that served it."""
    total = 0.0
    for r in records:
        for model, u in ([(it["model"], it) for it in r["iterations"]] if r.get("iterations") else [(r["served_by"], r["usage"])]):
            inp, outp, write, read = PRICES[model]
            total += (u["input_tokens"] * inp + u["output_tokens"] * outp + u["cache_creation_input_tokens"] * write
                      + u["cache_read_input_tokens"] * read) / 1e6
    return total
