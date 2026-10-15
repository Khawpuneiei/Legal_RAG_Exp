"""Minimal local LLM client for Ollama with a persistent response cache."""
from __future__ import annotations

import os
import time

import requests

from src.common import JsonCache, stable_hash

HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")


class OllamaLLM:
    def __init__(self, model: str = MODEL, num_ctx: int = 8192, cache_name: str = "llm"):
        self.model = model
        self.num_ctx = num_ctx
        self.cache = JsonCache(f"{cache_name}-{model.replace(':', '_')}")

    def generate(self, prompt: str, system: str = "", temperature: float = 0.0, seed: int = 0,
                 json_mode: bool = False, max_tokens: int = 512) -> dict:
        """Return {"text": ..., "latency_s": ..., "cached": bool}."""
        key = stable_hash(self.model, system, prompt, str(temperature), str(seed), str(json_mode), str(max_tokens), str(self.num_ctx))
        hit = self.cache.get(key)
        if hit is not None:
            return {**hit, "cached": True}
        body = {
            "model": self.model, "prompt": prompt, "system": system, "stream": False,
            "options": {"temperature": temperature, "seed": seed, "num_ctx": self.num_ctx, "num_predict": max_tokens},
        }
        if json_mode:
            body["format"] = "json"
        t0 = time.time()
        for attempt in range(3):
            try:
                r = requests.post(f"{HOST}/api/generate", json=body, timeout=600)
                r.raise_for_status()
                break
            except requests.RequestException:
                if attempt == 2:
                    raise
                time.sleep(5)
        out = {"text": r.json()["response"], "latency_s": round(time.time() - t0, 3)}
        self.cache.put(key, out)
        return {**out, "cached": False}

    def unload(self) -> None:
        try:
            requests.post(f"{HOST}/api/generate", json={"model": self.model, "keep_alive": 0}, timeout=60)
        except requests.RequestException:
            pass
