"""Embedding backend implementations.

Two backends; one protocol:

* :class:`local.LocalBackend` — sentence-transformers (default
  ``Qwen/Qwen3-Embedding-0.6B``).
* :class:`openai_compat.OpenAICompatibleBackend` — any provider that
  speaks OpenAI's ``POST /embeddings`` shape (Qwen DashScope, OpenAI,
  Zhipu, Voyage, self-hosted vLLM / Ollama / TEI, etc.).

:func:`build_backend` reads the active :class:`config.EmbeddingConfig`
and returns the concrete backend instance.
"""

from codemap_semantic_index.embedding.base import EmbeddingBackend
from codemap_semantic_index.embedding.factory import build_backend

__all__ = ["EmbeddingBackend", "build_backend"]
