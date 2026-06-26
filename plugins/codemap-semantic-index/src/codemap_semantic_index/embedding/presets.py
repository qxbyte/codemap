"""Preset cloud providers — base_url / default model / API key env hint.

Defined here as data so :mod:`cli` can render the interactive
``codemap embed backend set`` wizard without duplicating strings."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "CLOUD_PRESETS",
    "LOCAL_MODEL_CANDIDATES",
    "CloudPreset",
    "get_cloud_preset",
]


@dataclass(frozen=True)
class CloudPreset:
    """One row in the interactive provider menu."""

    provider: str
    label: str  # human-facing name (shown in the menu)
    base_url: str
    default_model: str
    dimensions: int  # all four presets land on 1024 by design
    api_key_env: str  # provider-specific env var fallback
    notes: str = ""


CLOUD_PRESETS: tuple[CloudPreset, ...] = (
    CloudPreset(
        provider="qwen",
        label="阿里云 DashScope · text-embedding-v3",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="text-embedding-v3",
        dimensions=1024,
        api_key_env="DASHSCOPE_API_KEY",
        notes="Recommended: same-source as the default local model (Qwen3-Embedding-0.6B).",
    ),
    CloudPreset(
        provider="openai",
        label="OpenAI · text-embedding-3-small (dim=1024)",
        base_url="https://api.openai.com/v1",
        default_model="text-embedding-3-small",
        dimensions=1024,
        api_key_env="OPENAI_API_KEY",
        notes="3-small / 3-large both default 1536/3072; we force dim=1024 for cross-backend parity.",
    ),
    CloudPreset(
        provider="zhipu",
        label="智谱 · embedding-3",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        default_model="embedding-3",
        dimensions=1024,
        api_key_env="ZHIPUAI_API_KEY",
    ),
    CloudPreset(
        provider="voyage",
        label="Voyage AI · voyage-3",
        base_url="https://api.voyageai.com/v1",
        default_model="voyage-3",
        dimensions=1024,
        api_key_env="VOYAGE_API_KEY",
        notes="Strong on English / code corpora.",
    ),
)


@dataclass(frozen=True)
class LocalModelCandidate:
    """One row in the ``codemap embed install`` interactive menu."""

    model_id: str
    label: str
    size_mb: int
    dimensions: int
    notes: str = ""


LOCAL_MODEL_CANDIDATES: tuple[LocalModelCandidate, ...] = (
    LocalModelCandidate(
        model_id="Qwen/Qwen3-Embedding-0.6B",
        label="Qwen/Qwen3-Embedding-0.6B (1024 dim, 32k context, multilingual SOTA)",
        size_mb=1200,
        dimensions=1024,
        notes="Recommended: same-source as Qwen cloud text-embedding-v3.",
    ),
    LocalModelCandidate(
        model_id="BAAI/bge-m3",
        label="BAAI/bge-m3 (1024 dim, 8k context, multilingual stable)",
        size_mb=560,
        dimensions=1024,
        notes="Smaller download.",
    ),
    LocalModelCandidate(
        model_id="BAAI/bge-large-zh-v1.5",
        label="BAAI/bge-large-zh-v1.5 (1024 dim, 512 context, Chinese-specialised)",
        size_mb=1300,
        dimensions=1024,
        notes="Pure-Chinese projects only — 512 ctx truncates long specs.",
    ),
)


def get_cloud_preset(provider: str) -> CloudPreset | None:
    for p in CLOUD_PRESETS:
        if p.provider == provider:
            return p
    return None
