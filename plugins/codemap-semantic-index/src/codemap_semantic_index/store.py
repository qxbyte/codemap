"""On-disk store: ``<project_root>/.ai-memory/_semantic/{chunks.json,
vectors.npy, model_id.txt, manifest.json}``.

Layout (mirrors the design in
``Obsidian/Notes/07-Ideas/AI-Enterprise-Delivery-System/2026-06-27-
p1-3-codemap-semantic-index-设计方案.md`` §5):

* ``chunks.json`` — sliced text + per-chunk metadata. Row order matches
  ``vectors.npy``. Changing model does NOT change this file.
* ``vectors.npy`` — ``numpy.save`` of a ``(n_chunks, dimensions)``
  float32 matrix. Changing model rewrites this whole file.
* ``model_id.txt`` — single line ``<backend>:<provider>:<model>`` (e.g.
  ``local:huggingface:Qwen/Qwen3-Embedding-0.6B`` or
  ``openai_compatible:qwen:text-embedding-v3``). Recall / embed compare
  this against the active backend at startup and refuse to load when
  it doesn't match without ``--rebuild``.
* ``manifest.json`` — ``{chunk_id: text_hash}`` so incremental embed
  knows which chunks need re-encoding.

Everything writes atomically (tmp + ``os.replace``)."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from codemap_semantic_index.chunker import Chunk

__all__ = [
    "ModelMismatch",
    "SemanticStore",
    "format_model_id",
    "parse_model_id",
]


@dataclass(frozen=True)
class ModelIdentity:
    backend: str
    provider: str
    model: str


def format_model_id(backend: str, provider: str | None, model: str) -> str:
    """Render the active model fingerprint as a single string."""
    return f"{backend}:{provider or 'default'}:{model}"


def parse_model_id(text: str) -> ModelIdentity:
    parts = text.strip().split(":", 2)
    if len(parts) != 3:
        raise ValueError(f"malformed model_id.txt: {text!r}")
    backend, provider, model = parts
    return ModelIdentity(backend=backend, provider=provider, model=model)


class ModelMismatch(RuntimeError):
    """Raised when on-disk model_id.txt disagrees with the active backend."""


class SemanticStore:
    """Read / write the four on-disk artefacts as a single unit."""

    CHUNKS = "chunks.json"
    VECTORS = "vectors.npy"
    MODEL_ID = "model_id.txt"
    MANIFEST = "manifest.json"

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.root = project_root / ".ai-memory" / "_semantic"

    # ---------- existence / discovery ----------

    @property
    def is_built(self) -> bool:
        """True when both chunks.json and vectors.npy exist."""
        return self.chunks_path.is_file() and self.vectors_path.is_file()

    @property
    def chunks_path(self) -> Path:
        return self.root / self.CHUNKS

    @property
    def vectors_path(self) -> Path:
        return self.root / self.VECTORS

    @property
    def model_id_path(self) -> Path:
        return self.root / self.MODEL_ID

    @property
    def manifest_path(self) -> Path:
        return self.root / self.MANIFEST

    # ---------- model_id check ----------

    def assert_model_matches(self, expected: str) -> None:
        """Raise :class:`ModelMismatch` if on-disk model_id.txt != expected.

        When no model_id.txt exists yet (fresh project) → pass silently;
        the caller is about to write it."""
        if not self.model_id_path.is_file():
            return
        on_disk = self.model_id_path.read_text(encoding="utf-8").strip()
        if on_disk != expected:
            raise ModelMismatch(
                f"semantic index was built with {on_disk!r} but the active "
                f"backend is {expected!r}; embeddings live in different "
                f"vector spaces and cannot be compared. Re-run "
                f"`codemap embed --rebuild` to rebuild with the active "
                f"backend."
            )

    # ---------- write ----------

    def write_all(
        self,
        chunks: list[Chunk],
        vectors: np.ndarray,
        model_id: str,
    ) -> None:
        """Atomic write of all four files.

        Vectors row order MUST match the chunks list. Caller is responsible
        for that ordering."""
        if len(chunks) != vectors.shape[0]:
            raise ValueError(f"chunk count ({len(chunks)}) != vector rows ({vectors.shape[0]})")
        self.root.mkdir(parents=True, exist_ok=True)

        # chunks.json
        chunks_payload: dict[str, Any] = {
            "schema_version": "1.0",
            "n_chunks": len(chunks),
            "model_id": model_id,
            "chunks": [c.to_dict() for c in chunks],
        }
        _atomic_write_text(
            self.chunks_path,
            json.dumps(chunks_payload, ensure_ascii=False, indent=2),
        )

        # vectors.npy
        _atomic_write_npy(self.vectors_path, vectors.astype(np.float32, copy=False))

        # model_id.txt
        _atomic_write_text(self.model_id_path, model_id + "\n")

        # manifest.json (chunk_id → text_hash)
        manifest = {c.chunk_id: c.text_hash for c in chunks}
        _atomic_write_text(
            self.manifest_path,
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )

    # ---------- read ----------

    def load_chunks(self) -> list[Chunk]:
        if not self.chunks_path.is_file():
            return []
        try:
            data = json.loads(self.chunks_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        raw_chunks = data.get("chunks") if isinstance(data, dict) else None
        if not isinstance(raw_chunks, list):
            return []
        out: list[Chunk] = []
        for entry in raw_chunks:
            if not isinstance(entry, dict):
                continue
            try:
                out.append(
                    Chunk(
                        chunk_id=entry["chunk_id"],
                        knowledge_id=entry["knowledge_id"],
                        category=entry["category"],
                        title=entry.get("title", ""),
                        h2_title=entry.get("h2_title", ""),
                        text=entry["text"],
                        source_md=entry["source_md"],
                        source_yml=entry["source_yml"],
                        text_hash=entry["text_hash"],
                    )
                )
            except KeyError:
                continue
        return out

    def load_vectors(self) -> np.ndarray | None:
        if not self.vectors_path.is_file():
            return None
        try:
            return np.load(self.vectors_path)
        except (OSError, ValueError):
            return None

    def load_manifest(self) -> dict[str, str]:
        if not self.manifest_path.is_file():
            return {}
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}

    def load_model_id(self) -> str | None:
        if not self.model_id_path.is_file():
            return None
        return self.model_id_path.read_text(encoding="utf-8").strip() or None


# ---------- atomic write helpers (tmp + replace) ----------


def _atomic_write_text(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, target)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _atomic_write_npy(target: Path, array: np.ndarray) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            np.save(fh, array, allow_pickle=False)
        os.replace(tmp, target)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
