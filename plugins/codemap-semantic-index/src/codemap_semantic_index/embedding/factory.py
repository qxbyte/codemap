"""Build an :class:`EmbeddingBackend` from an :class:`EmbeddingConfig`."""

from __future__ import annotations

from codemap_semantic_index.config import EmbeddingConfig
from codemap_semantic_index.embedding.base import EmbeddingBackend
from codemap_semantic_index.embedding.local import LocalBackend
from codemap_semantic_index.embedding.openai_compat import (
    OpenAICompatibleBackend,
)

__all__ = ["build_backend"]


def build_backend(cfg: EmbeddingConfig) -> EmbeddingBackend:
    """Return the concrete backend the config asks for.

    Validates the config minimally — bad values raise ``ValueError``
    so callers (CLI) can render an actionable message before any
    network / disk activity happens."""
    if cfg.backend == "local":
        return LocalBackend(
            model=cfg.model,
            dimensions=cfg.dimensions,
            provider=cfg.provider or "huggingface",
        )
    if cfg.backend == "openai_compatible":
        if not cfg.api_key:
            raise ValueError(
                "openai_compatible backend requires api_key — "
                "run `codemap embed backend set --provider <p> --api-key <k>` "
                "or set CODEMAP_EMBED_API_KEY"
            )
        if not cfg.base_url:
            raise ValueError(
                "openai_compatible backend requires base_url — "
                "run `codemap embed backend set --provider <p>` to pick a preset"
            )
        return OpenAICompatibleBackend(
            base_url=cfg.base_url,
            api_key=cfg.api_key,
            model=cfg.model,
            dimensions=cfg.dimensions,
            provider=cfg.provider or "openai_compatible",
        )
    raise ValueError(f"unknown backend {cfg.backend!r}; expected 'local' or 'openai_compatible'")
