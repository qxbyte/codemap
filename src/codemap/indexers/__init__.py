"""Pluggable indexer registry.

Built-in indexers are registered through `pyproject.toml`'s `codemap.indexers`
entry-point group on equal footing with third-party plugins (ADR-004, ADR-L001).
No language is privileged; the main repository ships only a reference
`_example_lang` indexer used to validate the end-to-end pipeline.
"""

from __future__ import annotations
