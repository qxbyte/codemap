"""Tests for the OpenAI-compatible cloud backend (httpx mocked)."""

from __future__ import annotations

import httpx
import numpy as np
import pytest
from codemap_semantic_index.embedding.openai_compat import (
    OpenAICompatibleBackend,
)


def _stub_client(handler) -> httpx.Client:
    transport = httpx.MockTransport(handler)
    return httpx.Client(
        transport=transport,
        headers={"Authorization": "Bearer test", "Content-Type": "application/json"},
    )


def test_encode_calls_embeddings_endpoint_with_correct_payload() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={
                "data": [
                    {"embedding": [0.1, 0.2, 0.3, 0.4]},
                    {"embedding": [0.5, 0.6, 0.7, 0.8]},
                ]
            },
        )

    backend = OpenAICompatibleBackend(
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        model="text-embedding-v3",
        dimensions=4,
        provider="qwen",
        http_client=_stub_client(handler),
    )
    arr = backend.encode(["hello", "world"])
    assert arr.shape == (2, 4)
    assert "https://api.example.com/v1/embeddings" in captured["url"]
    # JSON spacing depends on serialiser; just verify the key/value pairs are present.
    assert '"model"' in captured["body"]
    assert "text-embedding-v3" in captured["body"]
    assert '"dimensions"' in captured["body"]


def test_encode_empty_returns_zero_shape() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("should not call API for empty input")

    backend = OpenAICompatibleBackend(
        base_url="https://api.example.com/v1",
        api_key="k",
        model="m",
        dimensions=4,
        http_client=_stub_client(handler),
    )
    arr = backend.encode([])
    assert arr.shape == (0, 4)


def test_encode_l2_normalises_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"embedding": [3.0, 4.0, 0.0, 0.0]}]})

    backend = OpenAICompatibleBackend(
        base_url="https://api.example.com/v1",
        api_key="k",
        model="m",
        dimensions=4,
        http_client=_stub_client(handler),
    )
    arr = backend.encode(["x"])
    # Original norm is 5; normalised should have norm ≈ 1.0
    assert abs(float(np.linalg.norm(arr[0])) - 1.0) < 1e-5


def test_encode_batches_long_inputs() -> None:
    """Calling encode with > batch_size inputs should produce one HTTP
    call per batch."""
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        body = request.read().decode("utf-8")
        # Count "input" entries from payload
        import json as _json

        payload = _json.loads(body)
        return httpx.Response(
            200,
            json={"data": [{"embedding": [0.1] * 4} for _ in payload["input"]]},
        )

    backend = OpenAICompatibleBackend(
        base_url="https://api.example.com/v1",
        api_key="k",
        model="m",
        dimensions=4,
        batch_size=3,
        http_client=_stub_client(handler),
    )
    backend.encode(["a"] * 10)
    # 10 inputs / batch_size 3 → 4 calls
    assert call_count["n"] == 4


def test_http_error_raises_runtime_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server boom")

    backend = OpenAICompatibleBackend(
        base_url="https://api.example.com/v1",
        api_key="k",
        model="m",
        dimensions=4,
        http_client=_stub_client(handler),
    )
    with pytest.raises(RuntimeError, match="HTTP 500"):
        backend.encode(["x"])


def test_dim_mismatch_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"embedding": [0.1, 0.2, 0.3]}]},  # 3 dims, expected 4
        )

    backend = OpenAICompatibleBackend(
        base_url="https://api.example.com/v1",
        api_key="k",
        model="m",
        dimensions=4,
        http_client=_stub_client(handler),
    )
    with pytest.raises(RuntimeError, match="dim 3"):
        backend.encode(["x"])


def test_missing_api_key_raises() -> None:
    with pytest.raises(ValueError, match="api_key"):
        OpenAICompatibleBackend(
            base_url="x",
            api_key="",
            model="m",
            dimensions=4,
        )


def test_missing_base_url_raises() -> None:
    with pytest.raises(ValueError, match="base_url"):
        OpenAICompatibleBackend(
            base_url="",
            api_key="k",
            model="m",
            dimensions=4,
        )


def test_model_id_format() -> None:
    backend = OpenAICompatibleBackend(
        base_url="https://api.example.com/v1",
        api_key="k",
        model="m",
        dimensions=4,
        provider="qwen",
        http_client=_stub_client(lambda r: httpx.Response(200, json={"data": []})),
    )
    assert backend.model_id == "openai_compatible:qwen:m"
