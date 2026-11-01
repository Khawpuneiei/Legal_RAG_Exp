import src.common
from src.llm import ollama


class FakeResponse:
    def __init__(self, status, text="", data=None):
        self.status_code, self.text, self._data = status, text, data

    @property
    def ok(self):
        return self.status_code < 400

    def raise_for_status(self):
        if not self.ok:
            raise ollama.requests.HTTPError(f"{self.status_code} Server Error")

    def json(self):
        return self._data


def fake_server(monkeypatch, tmp_path, responses):
    monkeypatch.setattr(src.common, "CACHE", tmp_path)
    monkeypatch.setattr(ollama.time, "sleep", lambda s: None)
    calls = []

    def post(url, json, timeout):
        calls.append(json)
        return responses[min(len(calls), len(responses)) - 1]

    monkeypatch.setattr(ollama.requests, "post", post)
    return calls


def test_repeat_limit_abort_is_an_empty_reply_without_retries(monkeypatch, tmp_path):
    calls = fake_server(monkeypatch, tmp_path, [FakeResponse(500, '{"error":"prediction aborted, token repeat limit reached"}')])
    llm = ollama.OllamaLLM(cache_name="test")
    out = llm.generate("p", seed=2, json_mode=True)
    assert out["text"] == "" and out["done_reason"] == "repeat_limit" and len(calls) == 1
    assert llm.generate("p", seed=2, json_mode=True)["cached"] and len(calls) == 1


def test_other_server_errors_are_retried(monkeypatch, tmp_path):
    ok = FakeResponse(200, data={"response": "{}", "done_reason": "stop", "eval_count": 3})
    calls = fake_server(monkeypatch, tmp_path, [FakeResponse(500, '{"error":"model runner crashed"}'), ok])
    out = ollama.OllamaLLM(cache_name="test").generate("p")
    assert out["text"] == "{}" and out["done_reason"] == "stop" and len(calls) == 2
