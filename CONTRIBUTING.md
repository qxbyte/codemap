# Contributing to CodeMap

Thanks for your interest. CodeMap is a **language-neutral** code-index platform; we do not privilege any language or framework. Please read this guide before opening a PR.

## Ground rules

1. **Read the design first** — start with `docs/` (link to vault) and the project README. New behavior changes require updating the design document and (often) a new ADR.
2. **Language neutrality (ADR-L001)** — proposals that introduce special-casing for any language/framework will be asked to refactor to the generic plugin protocol. Indexers and bridges live in plugins, not core.
3. **Quality gates must pass** — `ruff`, `mypy --strict`, `pytest --cov`, `import-linter` are CI-enforced. Don't bypass.

## Dev setup

```bash
git clone https://github.com/qxbyte/codemap.git
cd codemap
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run quality gates locally
ruff format --check .
ruff check .
mypy
pytest
lint-imports
```

## Adding a new Indexer

A language indexer is an entry_point-registered class implementing `codemap.indexers.base.Indexer`:

```python
from codemap.indexers.base import Indexer, IndexResult, IndexContext
from pathlib import Path

class MyLangIndexer:
    name = "my_lang"
    version = "0.1.0"
    file_patterns = ["*.mylang"]
    languages = ["my_lang"]

    def supports(self, path: Path) -> bool:
        return path.suffix == ".mylang"

    def index_file(self, path: Path, source: bytes, ctx: IndexContext) -> IndexResult:
        # Parse, walk, build Symbol + Edge + Diagnostic lists, return IndexResult.
        ...
```

Register in your package's `pyproject.toml`:

```toml
[project.entry-points."codemap.indexers"]
my_lang = "my_pkg.my_indexer:MyLangIndexer"
```

**Acceptance checklist for an indexer PR**:

- [ ] ≥ 20 golden fixtures under `tests/fixtures/indexers/my_lang/`
- [ ] Unit test for `Indexer.supports`
- [ ] End-to-end CLI test through at least one real project
- [ ] Documentation at `docs/indexers/my_lang.md`
- [ ] CHANGELOG entry

## Adding a new Bridge

A bridge resolves cross-scheme relationships after all indexers finish:

```python
from codemap.core.bridge.base import Bridge, BridgeResult
from codemap.io.base import ReadOnlyStore

class MyBridge:
    name = "my_bridge"
    version = "0.1.0"
    requires: list[str] = []  # dependency on other bridges

    def resolve(self, store: ReadOnlyStore) -> BridgeResult:
        # Inspect symbols/edges, emit cross-scheme aliases or new edges.
        ...
```

Register:

```toml
[project.entry-points."codemap.bridges"]
my_bridge = "my_pkg.my_bridge:MyBridge"
```

## Commit & PR conventions

- Conventional commits style preferred: `feat(indexer): ...`, `fix(io): ...`, `docs(adr): ...`.
- PR description must link to:
  - The design-doc section being changed (if applicable)
  - Related ADR (or "no ADR needed" with reasoning)
  - Any Sprint task ID from the roadmap

## ADR workflow

For non-trivial decisions:

1. Copy `docs/adr/0000-template.md` to `docs/adr/NNNN-short-title.md`.
2. Open PR with status `Proposed`.
3. After review, status moves to `Accepted` / `Rejected` / `Superseded`.
4. Register the ADR in the design document's ADR Index table.

## Code of conduct

Be excellent to each other.
