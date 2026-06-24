"""Minimal OpenAI-compatible HTTP client for the optional ``codemap enrich``
CLI command.

Talks the OpenAI Chat Completions wire format, which both proper OpenAI,
Anthropic-via-proxy, Ollama, vLLM, and most aggregators speak. The only
runtime dependency is ``httpx`` (already widely co-installed with pydantic /
Anthropic SDK families). The plugin's optional ``[llm]`` extra pulls the
official ``anthropic`` SDK for users who want it instead — that path goes
through :class:`AnthropicClient` below.

The client satisfies the ``LlmClient`` Protocol in :mod:`codemap_aimemory.enrich`:

    class LlmClient(Protocol):
        model: str
        def describe(self, symbol: dict[str, Any]) -> dict[str, Any]: ...

``describe(symbol)`` returns ``{"business_meaning": str, "related_rules":
list[str]}``. Network / parse failures degrade gracefully — both keys come
back empty so the enrichment file still lands with the correct shape and
the orchestrator never crashes a Plan-4 pipeline on a transient LLM hiccup.
"""

from __future__ import annotations

import json
import os
from typing import Any

__all__ = ["AnthropicClient", "OpenAICompatibleClient", "build_client"]


_SYSTEM_PROMPT = (
    "You annotate code symbols for an internal knowledge graph. "
    "For each symbol you receive, return STRICT JSON with exactly two keys: "
    "`business_meaning` (a one-sentence Chinese or English description of "
    "what the symbol does in business terms) and `related_rules` (a list of "
    "short rule identifiers it implements; [] if none). Do not wrap the JSON "
    "in markdown, do not add commentary, do not include any other keys."
)


class OpenAICompatibleClient:
    """Works against any /v1/chat/completions endpoint (OpenAI, vLLM, Ollama
    + ``--openai-api`` adapter, LM Studio, OneAPI / Higress aggregators)."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 30.0,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def describe(self, symbol: dict[str, Any]) -> dict[str, Any]:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "codemap enrich requires httpx. "
                "Install with: pip install codemap-aimemory[llm]"
            ) from exc

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Symbol: {symbol.get('symbol_id')}\n"
                        f"Signature: {symbol.get('signature') or '(none)'}\n"
                        f"File: {symbol.get('file')}\n"
                        "Respond with the JSON object."
                    ),
                },
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError, ValueError):
            return {"business_meaning": None, "related_rules": []}
        return {
            "business_meaning": parsed.get("business_meaning"),
            "related_rules": list(parsed.get("related_rules") or []),
        }


class AnthropicClient:
    """Native Anthropic Messages API (`anthropic` SDK). Use this when the
    project already depends on the official SDK; otherwise the OpenAI-compat
    path covers Claude through the standard Bearer-token aggregators too."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str | None = None,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._base_url = base_url

    def describe(self, symbol: dict[str, Any]) -> dict[str, Any]:
        try:
            import anthropic  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "AnthropicClient requires the anthropic SDK. "
                "Install with: pip install codemap-aimemory[llm]"
            ) from exc

        client_kwargs: dict[str, Any] = {"api_key": self._api_key}
        if self._base_url:
            client_kwargs["base_url"] = self._base_url
        try:
            client = anthropic.Anthropic(**client_kwargs)
            response = client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Symbol: {symbol.get('symbol_id')}\n"
                            f"Signature: {symbol.get('signature') or '(none)'}\n"
                            f"File: {symbol.get('file')}\n"
                            "Respond with the JSON object only."
                        ),
                    }
                ],
            )
            text = "".join(block.text for block in response.content if hasattr(block, "text"))
            parsed = json.loads(text)
        except Exception:  # pragma: no cover - depends on SDK errors
            return {"business_meaning": None, "related_rules": []}
        return {
            "business_meaning": parsed.get("business_meaning"),
            "related_rules": list(parsed.get("related_rules") or []),
        }


def build_client(
    *,
    backend: str,
    model: str,
    api_key: str,
    base_url: str | None = None,
) -> Any:
    """Construct a client by backend keyword. Resolves OpenAI-style defaults.

    ``backend``:
      * ``"openai"`` / ``"openai-compatible"`` — :class:`OpenAICompatibleClient`,
        default base_url ``https://api.openai.com/v1``
      * ``"anthropic"`` — :class:`AnthropicClient` using the official SDK
      * ``"ollama"`` — :class:`OpenAICompatibleClient`, default base_url
        ``http://localhost:11434/v1``, ignores api_key
    """
    b = backend.lower()
    if b in {"openai", "openai-compatible"}:
        return OpenAICompatibleClient(
            model=model,
            api_key=api_key,
            base_url=base_url or "https://api.openai.com/v1",
        )
    if b == "anthropic":
        return AnthropicClient(model=model, api_key=api_key, base_url=base_url)
    if b == "ollama":
        return OpenAICompatibleClient(
            model=model,
            api_key=api_key or "ollama",
            base_url=base_url or "http://localhost:11434/v1",
        )
    raise ValueError(
        f"unknown LLM backend {backend!r}; expected openai / anthropic / ollama"
    )


def env_default(*names: str) -> str | None:
    """Return the first non-empty value among ``os.environ[name]`` for any
    ``name`` in ``names``. Used to thread CLI options through environment
    variables when the user doesn't pass them explicitly."""
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None
