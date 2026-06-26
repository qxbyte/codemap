"""Embedding backend configuration — ``~/.config/codemap/embedding.yaml``.

Mirrors the shape of :mod:`codemap_aimemory.config` so users see a
familiar surface. Two backend kinds:

* ``backend: local`` — sentence-transformers wrapper; ``model`` is a
  HuggingFace ``model_id`` (default ``Qwen/Qwen3-Embedding-0.6B``).
* ``backend: openai_compatible`` — POST ``{base_url}/embeddings``;
  ``provider`` is a free-form label (``qwen`` / ``openai`` / ``zhipu`` /
  ``voyage`` / ``custom``).

Resolution priority for every field (first non-empty wins):

1. CLI flag
2. Environment variable (``CODEMAP_EMBED_*`` then provider-specific fallbacks)
3. ``~/.config/codemap/embedding.yaml`` (or ``$XDG_CONFIG_HOME/...``)
4. Built-in defaults
"""

from __future__ import annotations

import contextlib
import os
import stat
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "DEFAULT_DIMENSIONS",
    "DEFAULT_LOCAL_MODEL",
    "EmbeddingConfig",
    "config_path",
    "env_default",
    "load",
    "save",
    "unset",
]

#: Default local sentence-transformers model — Qwen3-Embedding-0.6B.
#: Same-source training as cloud Qwen text-embedding-v3, so switching
#: backends preserves recall "feel" better than other model families.
DEFAULT_LOCAL_MODEL = "Qwen/Qwen3-Embedding-0.6B"

#: Default vector dimension. All 4 preset cloud providers + the default
#: local model align on 1024. Custom backends MUST match.
DEFAULT_DIMENSIONS = 1024


@dataclass
class EmbeddingConfig:
    """Persisted embedding backend settings.

    Either local OR openai-compatible — ``backend`` discriminates."""

    backend: str = "local"  # local | openai_compatible
    provider: str | None = None  # free-form label (huggingface / qwen / openai / ...)
    model: str = DEFAULT_LOCAL_MODEL
    base_url: str | None = None  # required when backend = openai_compatible
    api_key: str | None = None  # required when backend = openai_compatible
    dimensions: int = DEFAULT_DIMENSIONS

    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EmbeddingConfig:
        known = {"backend", "provider", "model", "base_url", "api_key", "dimensions"}
        return cls(
            backend=str(data.get("backend", "local")),
            provider=_as_optional_str(data.get("provider")),
            model=str(data.get("model", DEFAULT_LOCAL_MODEL)),
            base_url=_as_optional_str(data.get("base_url")),
            api_key=_as_optional_str(data.get("api_key")),
            dimensions=int(data.get("dimensions", DEFAULT_DIMENSIONS)),
            extra={k: v for k, v in data.items() if k not in known},
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Suppress noisy None / empty extra at write time.
        out: dict[str, Any] = {}
        for k in ("backend", "provider", "model", "base_url", "api_key", "dimensions"):
            v = d[k]
            if v not in (None, ""):
                out[k] = v
        if self.extra:
            out.update(self.extra)
        return out


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


# ---------- file path ----------


def _xdg_config_home() -> Path:
    raw = os.environ.get("XDG_CONFIG_HOME")
    if raw:
        return Path(raw)
    return Path.home() / ".config"


def config_path() -> Path:
    """Absolute path of ``~/.config/codemap/embedding.yaml`` (XDG-aware)."""
    return _xdg_config_home() / "codemap" / "embedding.yaml"


# ---------- IO ----------


def load() -> EmbeddingConfig:
    """Read the config file; return defaults when missing / corrupt."""
    path = config_path()
    if not path.is_file():
        return EmbeddingConfig()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return EmbeddingConfig()
    if not isinstance(data, dict):
        return EmbeddingConfig()
    return EmbeddingConfig.from_dict(data)


def save(cfg: EmbeddingConfig) -> Path:
    """Write the config file (creating parent dir + chmod 600)."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(cfg.to_dict(), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    with contextlib.suppress(OSError):
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600 — file carries api_key
    return path


def unset(key: str) -> EmbeddingConfig:
    """Remove a single field; return the resulting (re-saved) config."""
    cfg = load()
    valid = {"provider", "model", "base_url", "api_key", "dimensions", "backend"}
    if key not in valid:
        raise KeyError(f"unknown config key '{key}'; valid: {sorted(valid)}")
    if key == "backend":
        cfg.backend = "local"
        cfg.model = DEFAULT_LOCAL_MODEL
        cfg.provider = "huggingface"
        cfg.base_url = None
        cfg.api_key = None
    elif key == "dimensions":
        cfg.dimensions = DEFAULT_DIMENSIONS
    else:
        setattr(cfg, key, None)
    save(cfg)
    return cfg


# ---------- env fallback ----------


def env_default(*names: str) -> str | None:
    """Return the first non-empty env var value among ``names`` (or None)."""
    for name in names:
        v = os.environ.get(name)
        if v:
            return v.strip()
    return None
