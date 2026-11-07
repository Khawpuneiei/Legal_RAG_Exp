from types import SimpleNamespace

import pytest

import src.common

pytest.importorskip("anthropic")   # the `experiments` extra; CI installs base + dev only
from src.llm import claude  # noqa: E402


def tokens(i, o, **extra):
    return SimpleNamespace(input_tokens=i, output_tokens=o, cache_creation_input_tokens=None, cache_read_input_tokens=None, **extra)


def reply(text="An answer [1].", stop="end_turn", model="claude-opus-5-5", blocks=None, iterations=None):
    content = blocks if blocks is not None else [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)]
    usage = tokens(1000, 500, iterations=iterations)
    details = SimpleNamespace(type="refusal", category="cyber", explanation="") if stop == "refusal" else None
    return SimpleNamespace(content=content, stop_reason=stop, model=model, usage=usage, stop_details=details)


@pytest.fixture
def fake(monkeypatch, tmp_path):
    monkeypatch.setattr(src.common, "CACHE", tmp_path)
    calls, replies = [], []

    def create(**request):
        calls.append(request)
        return replies.pop(0)

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    return client, calls, replies


def test_request_shape_and_cache(fake):
    client, calls, replies = fake
    replies.append(reply())
    chat = claude.ClaudeChat(client=client, cache_name="t")
    assert chat.complete("sys", "q") == "An answer [1]." and chat.name == "claude:claude-opus-5-5"
    sent = calls[0]
    assert sent["output_config"] == {"effort": "medium"} and sent["system"] == "sys" and sent["max_tokens"] == 16000
    assert sent["fallbacks"] == "default" and sent["betas"] == [claude.FALLBACK_BETA]
    assert not {"temperature", "top_p", "top_k", "thinking"} & sent.keys()   # 400 on API version 2026-10-21 / always on
    again = chat.generate("sys", "q")
    assert again["cached"] and len(calls) == 1 and again["usage"]["output_tokens"] == 500


def test_refusal_is_an_empty_reply(fake):
    client, _, replies = fake
    replies.append(reply(stop="refusal", blocks=[]))
    out = claude.ClaudeChat(client=client, cache_name="t").generate("sys", "q")
    assert out["text"] == "" and out["stop_reason"] == "refusal" and out["refusal_category"] == "cyber"


def test_haiku_sends_no_fallbacks_and_cost_uses_the_serving_model(fake):
    client, calls, replies = fake
    replies.append(reply(model="claude-haiku-5-5"))
    out = claude.ClaudeChat("claude-haiku-5-5", effort="low", client=client, cache_name="t").generate("s", "q")
    assert "fallbacks" not in calls[0] and calls[0]["output_config"] == {"effort": "low"}
    assert claude.cost([out]) == pytest.approx((1000 * 0.10 + 500 * 0.50) / 1e6)
    fell_back = {**out, "served_by": "claude-opus-4-8"}
    assert claude.cost([fell_back]) == pytest.approx((1000 * 5.0 + 500 * 25.0) / 1e6)


def test_a_fallback_is_priced_attempt_by_attempt(fake):
    client, _, replies = fake
    attempts = [tokens(1000, 200, type="message", model="claude-opus-5-5"),
                tokens(1000, 300, type="fallback_message", model="claude-opus-4-8")]
    replies.append(reply(model="claude-opus-4-8", iterations=attempts))
    out = claude.ClaudeChat(client=client, cache_name="t").generate("s", "q")
    assert [it["model"] for it in out["iterations"]] == ["claude-opus-5-5", "claude-opus-4-8"]
    assert claude.cost([out]) == pytest.approx((1000 * 4.0 + 200 * 20.0 + 1000 * 5.0 + 300 * 25.0) / 1e6)
