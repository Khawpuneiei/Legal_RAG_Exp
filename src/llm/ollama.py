"""Minimal local LLM client for Ollama with a persistent response cache.

Also speaks the OpenAI-compatible chat API (LLM_BASE_URL), so the production app can point the same
code at a LiteLLM gateway, Azure OpenAI or any OpenAI-compatible endpoint (docs/architecture.md).
"""
from __future__ import annotations

import os
import threading
import time

import requests

from src.common import JsonCache, stable_hash

HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
_LOCK = threading.Lock()


def approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class OllamaLLM:
    def __init__(self, model: str = MODEL, num_ctx: int = 8192, cache_name: str = "llm"):
        self.model = model
        self.num_ctx = num_ctx
        self.cache = JsonCache(f"{cache_name}-{model.replace(':', '_')}")

    def generate(self, prompt: str, system: str = "", temperature: float = 0.0, seed: int = 0,
                 json_mode: bool = False, max_tokens: int = 512) -> dict:
        """Return {"text", "latency_s", "cached", "prompt_tokens", "completion_tokens"}."""
        key = stable_hash(self.model, system, prompt, str(temperature), str(seed), str(json_mode), str(max_tokens), str(self.num_ctx))
        hit = self.cache.get(key)
        if hit is not None:
            out = dict(hit)
            out.setdefault("prompt_tokens", approx_tokens(system + prompt))
            out.setdefault("completion_tokens", approx_tokens(out["text"]))
            return {**out, "cached": True}
        body = {
            "model": self.model, "prompt": prompt, "system": system, "stream": False,
            "options": {"temperature": temperature, "seed": seed, "num_ctx": self.num_ctx, "num_predict": max_tokens},
        }
        if json_mode:
            body["format"] = "json"
        t0 = time.time()
        for attempt in range(4):
            try:
                r = requests.post(f"{HOST}/api/generate", json=body, timeout=900)
                r.raise_for_status()
                break
            except requests.RequestException:
                if attempt == 3:
                    raise
                time.sleep(10)
        data = r.json()
        out = {"text": data["response"], "latency_s": round(time.time() - t0, 3),
               "prompt_tokens": data.get("prompt_eval_count") or approx_tokens(system + prompt),
               "completion_tokens": data.get("eval_count") or approx_tokens(data["response"])}
        with _LOCK:
            self.cache.put(key, out)
        return {**out, "cached": False}

    def unload(self) -> None:
        try:
            requests.post(f"{HOST}/api/generate", json={"model": self.model, "keep_alive": 0}, timeout=60)
        except requests.RequestException:
            pass


class OpenAICompatLLM:
    """Same interface as OllamaLLM for any OpenAI-compatible /chat/completions endpoint (LiteLLM, Azure, Groq...).

    The key is read from the environment (LLM_API_KEY); it is never logged or cached.
    """

    def __init__(self, base_url: str, model: str, api_key_env: str = "LLM_API_KEY", timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key_env = api_key_env
        self.timeout = timeout

    def generate(self, prompt: str, system: str = "", temperature: float = 0.0, seed: int = 0,
                 json_mode: bool = False, max_tokens: int = 512) -> dict:
        headers = {"Content-Type": "application/json"}
        key = os.environ.get(self.api_key_env)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        body = {"model": self.model, "temperature": temperature, "seed": seed, "max_tokens": max_tokens,
                "messages": ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        t0 = time.time()
        r = requests.post(f"{self.base_url}/chat/completions", json=body, headers=headers, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        usage = data.get("usage") or {}
        text = data["choices"][0]["message"]["content"] or ""
        return {"text": text, "latency_s": round(time.time() - t0, 3), "cached": False,
                "prompt_tokens": usage.get("prompt_tokens") or approx_tokens(system + prompt),
                "completion_tokens": usage.get("completion_tokens") or approx_tokens(text)}

    def unload(self) -> None:  # nothing to free for a remote endpoint
        pass
