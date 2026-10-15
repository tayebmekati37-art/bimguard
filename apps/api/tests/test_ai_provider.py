import asyncio

import httpx
import pytest

from app.ai.provider import (
    AIProviderError,
    OpenAICompatibleProvider,
    ScriptedProvider,
)

# Capture the real class BEFORE any monkeypatching.
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _run(coro):
    return asyncio.run(coro)


def _stub_client(handler):
    """Return a factory that builds a real AsyncClient with a mock transport."""
    transport = httpx.MockTransport(handler)

    def factory(**kwargs):
        kwargs.pop("timeout", None)
        kwargs.pop("transport", None)
        return _REAL_ASYNC_CLIENT(transport=transport, **kwargs)

    return factory


def test_scripted_dict_match():
    p = ScriptedProvider({"A-101": "reply A", "S-201": "reply S"})
    assert _run(p.complete("sys", "tell me about A-101")) == "reply A"
    assert _run(p.complete("sys", "tell me about S-201")) == "reply S"
    assert len(p.calls) == 2


def test_scripted_no_match_raises():
    p = ScriptedProvider({"A-101": "reply A"})
    with pytest.raises(AIProviderError):
        _run(p.complete("sys", "unknown"))


def test_scripted_list_order():
    p = ScriptedProvider(["one", "two", "three"])
    assert _run(p.complete("s", "u")) == "one"
    assert _run(p.complete("s", "u")) == "two"
    assert _run(p.complete("s", "u")) == "three"
    with pytest.raises(AIProviderError):
        _run(p.complete("s", "u"))


def test_openai_success(monkeypatch):
    def handler(request):
        assert request.url.path.endswith("/chat/completions")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "hello world"}}]},
        )

    monkeypatch.setattr("httpx.AsyncClient", _stub_client(handler))
    p = OpenAICompatibleProvider(base_url="http://test.local/v1", api_key="k", model="m")
    assert _run(p.complete("sys", "user")) == "hello world"


def test_openai_non_200(monkeypatch):
    def handler(request):
        return httpx.Response(500, text="boom")

    monkeypatch.setattr("httpx.AsyncClient", _stub_client(handler))
    p = OpenAICompatibleProvider(base_url="http://test.local/v1", model="m")
    with pytest.raises(AIProviderError) as ei:
        _run(p.complete("sys", "user"))
    assert "500" in str(ei.value)


def test_openai_bad_json(monkeypatch):
    def handler(request):
        return httpx.Response(200, text="not json", headers={"Content-Type": "text/plain"})

    monkeypatch.setattr("httpx.AsyncClient", _stub_client(handler))
    p = OpenAICompatibleProvider(base_url="http://test.local/v1", model="m")
    with pytest.raises(AIProviderError) as ei:
        _run(p.complete("sys", "user"))
    assert "json" in str(ei.value).lower()


def test_openai_unexpected_shape(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"choices": []})

    monkeypatch.setattr("httpx.AsyncClient", _stub_client(handler))
    p = OpenAICompatibleProvider(base_url="http://test.local/v1", model="m")
    with pytest.raises(AIProviderError):
        _run(p.complete("sys", "user"))


def test_openai_timeout(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("too slow")

    monkeypatch.setattr("httpx.AsyncClient", _stub_client(handler))
    p = OpenAICompatibleProvider(base_url="http://test.local/v1", model="m")
    with pytest.raises(AIProviderError) as ei:
        _run(p.complete("sys", "user"))
    assert "timeout" in str(ei.value).lower()


def test_openai_not_configured(monkeypatch):
    monkeypatch.delenv("AI_BASE_URL", raising=False)
    monkeypatch.delenv("AI_MODEL", raising=False)
    p = OpenAICompatibleProvider()
    with pytest.raises(AIProviderError):
        _run(p.complete("sys", "user"))


def test_openai_reads_env(monkeypatch):
    def handler(request):
        assert request.url.host == "env.local"
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setenv("AI_BASE_URL", "http://env.local/v1")
    monkeypatch.setenv("AI_MODEL", "env-model")
    monkeypatch.setattr("httpx.AsyncClient", _stub_client(handler))
    p = OpenAICompatibleProvider()
    assert _run(p.complete("sys", "user")) == "ok"