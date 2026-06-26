# Changelog — codemap-semantic-index

This plugin's version is **independent** of `codemap-core` lockstep —
it's an opt-in semantic ranker, not part of the L1 indexing core.

## 0.1.0 (2026-06-27)

First release. Closes AI-EDS roadmap **P1-3**.

### What it does

Registers an embedding-based ranker into `codemap recall` via the
`codemap.recall_hooks` entry-point group (introduced in `codemap-core`
0.4.1). `codemap-aimemory` RRF-fuses our ranking with its token
ranking and multiplies by freshness (P4-2), so installing this plugin
upgrades recall from token-only to hybrid semantic + token + freshness
with zero user code change.

### Modules

- `chunker` — markdown → chunks. Splits on `##` headings; over-long
  sections re-split with sliding windows (500 tokens / 50 overlap).
  Every chunk text is prefixed `"<knowledge_id> / <h2_title>\n\n..."`
  so embeddings have an anchor to the source doc.
- `store` — atomic on-disk store under `.ai-memory/_semantic/`:
  `chunks.json` (model-independent metadata) + `vectors.npy`
  (model-specific 1024-dim float32) + `model_id.txt` (active
  backend fingerprint) + `manifest.json` (text_hash → chunk_id for
  incremental).
- `config` — `~/.config/codemap/embedding.yaml` reader/writer; chmod 600.
- `embedding/local.py` — sentence-transformers wrapper, default
  `Qwen/Qwen3-Embedding-0.6B` (1024-dim, 32k context, same-source as
  Qwen cloud text-embedding-v3). Lazy-imports `sentence_transformers`
  so plain `--help` doesn't pay torch boot cost.
- `embedding/openai_compat.py` — `POST {base_url}/embeddings` over
  httpx. Handles 4 preset providers (Qwen / OpenAI / Zhipu / Voyage)
  + custom (self-hosted vLLM / Ollama / TEI / Jina).
- `indexer` — `rebuild_index` (full) + `incremental_index` (hash-diff;
  only re-encode chunks whose text changed); refuses on model mismatch.
- `recall_hook` — entry-point function. Loads the on-disk store, encodes
  the query, computes cosine similarities (vectors are L2-normalised so
  dot-product), aggregates chunks → knowledge_id (best chunk wins),
  returns hook-contract-shaped candidates with freshness already
  computed. Failure modes (no store / model mismatch / network down)
  all silently return `[]` so recall never crashes.

### CLI — `codemap embed`

11 sub-commands organised in two groups:

- `codemap embed [--rebuild | --incremental | --dry-run | --project P]`
  — main embed pipeline; default is incremental.
- `codemap embed install [<model_id>]` — interactive picker (3 preset
  candidates + custom) or direct install.
- `codemap embed list` — show locally downloaded HF models, mark active.
- `codemap embed use <model_id>` — switch active local model; prints
  rebuild hint.
- `codemap embed backend set [--provider P --api-key K --base-url U
  --model M --dimensions N]` — configure local or cloud backend.
  Interactive picker when no `--provider`. Auto-fills base_url / model /
  dimensions from preset.
- `codemap embed backend show` — print effective config (api key masked).
- `codemap embed backend reset` — back to local defaults.
- `codemap embed backend path` — print config file location.

### Dependencies

- `codemap-core>=0.4.1` (entry-point group)
- `codemap-aimemory>=0.4.1` (freshness + recall infrastructure reused)
- `numpy>=1.24` (vector math)
- `httpx>=0.27` (cloud backend HTTP)
- `pyyaml>=6.0`, `typer>=0.12`
- `sentence-transformers>=3.0` — default install includes this (pulls
  torch ~200MB) so `codemap embed install` works out of the box

### Tests

66 unit tests covering chunker (10) + store (12) + config (9) +
openai_compat backend (8) + indexer (8) + recall_hook (8) + cli (11).
All deterministic — no network, no real embedding model download in
tests (uses a hashing fake backend that produces stable 4-dim unit
vectors).

### Design doc

`Obsidian/Notes/07-Ideas/AI-Enterprise-Delivery-System/2026-06-27-p1-3-codemap-semantic-index-设计方案.md`
