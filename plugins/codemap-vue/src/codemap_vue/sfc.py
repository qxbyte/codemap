"""Vue SFC (Single File Component) top-level extractor.

``tree-sitter-vue`` is not published on PyPI. The official Vue ecosystem
parses ``.vue`` files with a hand-written HTML scanner from
``@vue/compiler-sfc``; we mirror the minimum we need with a small
regex-driven scanner that locates the top-level ``<script>`` block (and
nothing else — ``<template>`` and ``<style>`` are deliberately ignored).

The scanner is intentionally permissive about malformed input: a missing
``</script>`` closing tag still produces a block that runs to EOF, so
indexing partial / in-progress files still yields useful symbols.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

ScriptLang = Literal["ts", "tsx", "js", "jsx"]

_SCRIPT_OPEN_RE = re.compile(
    rb"<script\b([^>]*)>",  # captures attributes inside the open tag
    re.IGNORECASE,
)
_SCRIPT_CLOSE_RE = re.compile(rb"</script\s*>", re.IGNORECASE)
_LANG_ATTR_RE = re.compile(
    rb"""\blang\s*=\s*(?P<q>["'])(?P<lang>[^"']+)(?P=q)""",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ScriptBlock:
    """One ``<script>`` block extracted from a .vue file.

    ``lang`` is normalised to one of ``"ts" | "tsx" | "js" | "jsx"``;
    defaults to ``"js"`` if no ``lang=`` attribute is present.

    ``content`` is the **bytes between the opening and closing tag**,
    not including the tags themselves.

    ``content_start_offset`` is the byte offset within the original
    file where ``content`` begins; it is used by the indexer to
    translate AST line numbers back to source-file coordinates.

    ``content_start_line`` is the 1-based line number in the original
    file where ``content`` begins.
    """

    lang: ScriptLang
    content: bytes
    content_start_offset: int
    content_start_line: int


def extract_script_blocks(source: bytes) -> list[ScriptBlock]:
    """Locate every top-level ``<script>`` block in a Vue SFC.

    Standard Vue 3 SFCs hold at most two ``<script>`` blocks: a normal
    one and a ``<script setup>`` one. We return them in the order they
    appear. Inner blocks (nested ``<script>`` inside a string literal
    or template) are not unlikely, but for top-level SFC parsing the
    naive scan is correct in practice.
    """
    blocks: list[ScriptBlock] = []
    cursor = 0
    while cursor < len(source):
        open_match = _SCRIPT_OPEN_RE.search(source, cursor)
        if open_match is None:
            break
        attrs = open_match.group(1) or b""
        content_start = open_match.end()
        close_match = _SCRIPT_CLOSE_RE.search(source, content_start)
        content_end = close_match.start() if close_match is not None else len(source)
        content = source[content_start:content_end]
        lang = _detect_lang(attrs)
        blocks.append(
            ScriptBlock(
                lang=lang,
                content=content,
                content_start_offset=content_start,
                content_start_line=source[:content_start].count(b"\n") + 1,
            )
        )
        cursor = close_match.end() if close_match is not None else content_end
    return blocks


def _detect_lang(attrs: bytes) -> ScriptLang:
    """Detect ``lang=`` from the bytes inside ``<script ...>``."""
    match = _LANG_ATTR_RE.search(attrs)
    if match is None:
        return "js"
    raw = match.group("lang").decode("ascii", errors="replace").strip().lower()
    if raw in {"ts", "typescript"}:
        return "ts"
    if raw == "tsx":
        return "tsx"
    if raw == "jsx":
        return "jsx"
    return "js"
