# codemap-semantic-index

Embedding-based semantic recall plugin for [codemap](https://github.com/qxbyte/codemap).

Registers an embedding ranker into `codemap recall` via the `codemap.recall_hooks` entry-point group (introduced in `codemap-core` 0.4.1). `codemap-aimemory` automatically RRF-fuses the embedding ranking with its token ranking and applies freshness decay (P4-2).

## Install

```bash
pipx inject codemap codemap-semantic-index
# pulls sentence-transformers + torch (~200MB)

# Pick + download a local model (1.2GB default)
codemap embed install                   # interactive picker
codemap embed install BAAI/bge-m3       # direct

# First embed (writes <project>/.ai-memory/_semantic/)
codemap embed

# Now `codemap recall` does double-path (token + embedding) + RRF + freshness
codemap recall '<query>' --with-content
```

## Default model

`Qwen/Qwen3-Embedding-0.6B` (1024 dim, 32k context, 1.2GB). Same-source training as the Qwen cloud `text-embedding-v3`, so switching to cloud preserves recall "feel".

## Cloud backend (any OpenAI-compatible embedding API)

```bash
codemap embed backend set    # interactive picker (qwen / openai / zhipu / voyage / custom)
codemap embed backend show
codemap embed backend reset  # back to local
```

Four preset providers + `custom` for self-hosted vLLM / Ollama / TEI. Config persists to `~/.config/codemap/embedding.yaml` (chmod 600).

## Storage

```
<project_root>/.ai-memory/_semantic/
├── chunks.json    chunked text + metadata (model-independent)
├── vectors.npy    (n_chunks, 1024) float32 (model-specific)
├── model_id.txt   active backend fingerprint
└── manifest.json  text_hash → chunk_id (drives incremental)
```

Switching models requires `codemap embed --rebuild` (different vector spaces are not comparable).

## Design doc

`Obsidian/Notes/07-Ideas/AI-Enterprise-Delivery-System/2026-06-27-p1-3-codemap-semantic-index-设计方案.md` — full spec including chunker / RRF / freshness integration.
