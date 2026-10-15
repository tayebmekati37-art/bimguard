"""AI provider abstraction.

OpenAICompatibleProvider talks to any OpenAI-compatible API (OpenAI,
Ollama, LM Studio, vLLM, etc). Config comes from env vars at call time:
AI_BASE_URL, AI_API_KEY (optional), AI_MODEL.

ScriptedProvider is for tests: no network, deterministic.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any

import httpx


class AIProviderError(Exception):
    """Any failure calling an AI provider."""


class AIProvider(ABC):
    @abstractmethod
    async def complete(self, system: str, user: str) -> str:
        """Return the assistant's text for the given system + user prompt."""


class OpenAICompatibleProvider(AIProvider):
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    def _config(self) -> tuple[str, str, str]:
        base = self._base_url or os.environ.get("AI_BASE_URL", "")
        key = self._api_key or os.environ.get("AI_API_KEY", "")
        model = self._model or os.environ.get("AI_MODEL", "")
        return base.rstrip("/"), key, model

    async def complete(self, system: str, user: str) -> str:
        base, key, model = self._config()
        if not base or not model:
            raise AIProviderError("AI provider not configured (AI_BASE_URL / AI_MODEL)")

        url = f"{base}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as e:
            raise AIProviderError(f"timeout: {e}") from e
        except httpx.HTTPError as e:
            raise AIProviderError(f"http error: {e}") from e

        if resp.status_code != 200:
            raise AIProviderError(f"status {resp.status_code}: {resp.text[:200]}")

        try:
            data = resp.json()
        except ValueError as e:
            raise AIProviderError(f"bad json: {e}") from e

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise AIProviderError(f"unexpected response shape: {e}") from e


class ScriptedProvider(AIProvider):
    """Deterministic provider for tests.

    responses may be:
      - dict[str, str]: match a substring of the user prompt -> reply
      - list[str]: return replies in order
    """

    def __init__(self, responses: dict[str, str] | list[str]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, str]] = []

    async def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if isinstance(self._responses, dict):
            for needle, reply in self._responses.items():
                if needle in user:
                    return reply
            raise AIProviderError(f"no scripted response matches: {user[:100]!r}")
        if isinstance(self._responses, list):
            if not self._responses:
                raise AIProviderError("no scripted responses left")
            return self._responses.pop(0)
        raise AIProviderError("invalid scripted responses")