"""Markdown → chunks for the semantic index.

Source: ``<project_root>/knowledge-base/{rules,business,modules,cases,
pitfalls}/*.md`` (written by ``specode-distill`` 3.0+ and ``task-swarm``
0.6+ — see specode-distill's ``references/doc-template.md`` for the
human-readable templates these files follow).

Algorithm (regex-only — no markdown lib so the chunker stays a
dependency-free wheel of its own):

1. Strip YAML frontmatter (``---`` ... ``---``)
2. Read the H1 (``# ...``) as the document title
3. Split the body on ``^## `` headings; each section = ``(h2_title, body)``
4. Body sections whose token count exceeds ``MAX_TOKENS`` are split with
   a sliding window (``WINDOW_TOKENS`` / ``WINDOW_OVERLAP``)
5. Each emitted chunk's text is prefixed with the title path
   ``"<knowledge_id> / <h2_title>\\n\\n<body>"`` so embedding models
   anchor on the right doc even when the body is a generic snippet.

Token counting is approximate: 1 token ≈ 4 characters for English /
2 characters for Chinese. The whole pipeline tolerates being slightly
off — a longer chunk gets one extra sliding-window slice; nothing
breaks."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "MAX_TOKENS",
    "WINDOW_OVERLAP",
    "WINDOW_TOKENS",
    "Chunk",
    "approx_token_count",
    "chunk_knowledge_base",
    "chunk_markdown",
]

#: Body sections longer than this get split into sliding windows.
MAX_TOKENS = 1000
#: Sliding window size when splitting an over-long section.
WINDOW_TOKENS = 500
#: Token overlap between adjacent windows (preserves boundary context).
WINDOW_OVERLAP = 50

#: Categories under ``knowledge-base/`` recognised by spec-distill v3.
KNOWLEDGE_CATEGORIES: tuple[str, ...] = (
    "rules",
    "business",
    "modules",
    "cases",
    "pitfalls",
)


@dataclass
class Chunk:
    """One unit of text fed to the embedding model.

    ``chunk_id`` is stable across re-runs (knowledge_id + h2 slug +
    optional window index) so incremental embedding can hash-compare and
    only re-encode the chunks whose ``text`` changed.
    """

    chunk_id: str
    knowledge_id: str
    category: str  # rules / business / modules / cases / pitfalls
    title: str  # the H1 of the md doc
    h2_title: str  # the H2 of the section this chunk came from
    text: str  # prefixed text fed to the embedder
    source_md: str  # path relative to project_root
    source_yml: str  # twin yml path under .ai-memory/knowledge/
    text_hash: str  # sha1 of text — incremental diff key

    def to_dict(self) -> dict[str, str]:
        return {
            "chunk_id": self.chunk_id,
            "knowledge_id": self.knowledge_id,
            "category": self.category,
            "title": self.title,
            "h2_title": self.h2_title,
            "text": self.text,
            "source_md": self.source_md,
            "source_yml": self.source_yml,
            "text_hash": self.text_hash,
        }


# ---------- core algorithm ----------


_FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
# A heading line is "## ..." OR "### ..." (we split at the same depth as
# H2 only; H3 stays inside its parent section).
_H2_SPLIT_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _strip_frontmatter(text: str) -> str:
    return _FRONTMATTER_RE.sub("", text, count=1)


def _extract_h1(text: str) -> str:
    m = _H1_RE.search(text)
    return m.group(1).strip() if m else ""


def _split_h2_sections(body: str) -> list[tuple[str, str]]:
    """Return ``[(h2_title, section_body), ...]``. Content before the
    first H2 lands as ``("", preamble)``; sections without a body are
    dropped."""
    # Find all H2 positions; iterate to build slices.
    matches = list(_H2_SPLIT_RE.finditer(body))
    if not matches:
        stripped = body.strip()
        return [("", stripped)] if stripped else []

    out: list[tuple[str, str]] = []
    # Preamble (text before first H2).
    preamble = body[: matches[0].start()].strip()
    if preamble:
        out.append(("", preamble))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        section_body = body[m.end() : end].strip()
        if section_body:
            out.append((m.group(1).strip(), section_body))
    return out


def approx_token_count(text: str) -> int:
    """Conservative ≈ token estimator: 1 token per 2 CJK chars,
    1 per 4 ASCII chars. Off by ~20% vs real BPE but consistent."""
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    other = len(text) - cjk
    return max(1, cjk // 2 + other // 4)


def _sliding_split(text: str) -> Iterator[str]:
    """Split an over-long section into windows of ~WINDOW_TOKENS each.

    Uses character indices proportional to the token estimator above so a
    pure-CJK section yields 2x as many chars per window as a pure-ASCII
    one (the inverse of the token math)."""
    cjk_ratio = sum(1 for ch in text if "一" <= ch <= "鿿") / max(1, len(text))
    chars_per_token = 2 if cjk_ratio > 0.5 else 4
    window_chars = WINDOW_TOKENS * chars_per_token
    overlap_chars = WINDOW_OVERLAP * chars_per_token
    step = max(1, window_chars - overlap_chars)
    i = 0
    while i < len(text):
        yield text[i : i + window_chars]
        if i + window_chars >= len(text):
            return
        i += step


def chunk_markdown(
    md_text: str,
    *,
    knowledge_id: str,
    category: str,
    source_md: str,
    source_yml: str,
) -> list[Chunk]:
    """Turn one md document into a list of :class:`Chunk` ready for
    embedding."""
    stripped = _strip_frontmatter(md_text)
    title = _extract_h1(stripped)
    # Remove the H1 line itself before sectioning so the preamble doesn't
    # carry the heading text twice.
    if title:
        stripped = _H1_RE.sub("", stripped, count=1).lstrip("\n")
    sections = _split_h2_sections(stripped)

    out: list[Chunk] = []
    for h2_title, section_body in sections:
        h2_slug = _slug(h2_title) if h2_title else "_preamble"
        if approx_token_count(section_body) <= MAX_TOKENS:
            out.append(
                _build_chunk(
                    chunk_id=f"{knowledge_id}::{h2_slug}",
                    knowledge_id=knowledge_id,
                    category=category,
                    title=title,
                    h2_title=h2_title,
                    section_body=section_body,
                    source_md=source_md,
                    source_yml=source_yml,
                )
            )
            continue
        # Over-long → sliding-window split
        for w_idx, window in enumerate(_sliding_split(section_body)):
            out.append(
                _build_chunk(
                    chunk_id=f"{knowledge_id}::{h2_slug}::w{w_idx}",
                    knowledge_id=knowledge_id,
                    category=category,
                    title=title,
                    h2_title=h2_title,
                    section_body=window,
                    source_md=source_md,
                    source_yml=source_yml,
                )
            )
    return out


_SLUG_RE = re.compile(r"[^a-z0-9一-鿿]+")


def _slug(text: str) -> str:
    return _SLUG_RE.sub("-", text.lower()).strip("-") or "section"


def _build_chunk(
    *,
    chunk_id: str,
    knowledge_id: str,
    category: str,
    title: str,
    h2_title: str,
    section_body: str,
    source_md: str,
    source_yml: str,
) -> Chunk:
    # Prefix: title path so the embedding has the "which doc / which
    # section" anchor even when the body is a generic sentence.
    prefix = f"{knowledge_id} / {h2_title}" if h2_title else knowledge_id
    text = f"{prefix}\n\n{section_body}"
    text_hash = hashlib.sha1(text.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
    return Chunk(
        chunk_id=chunk_id,
        knowledge_id=knowledge_id,
        category=category,
        title=title,
        h2_title=h2_title,
        text=text,
        source_md=source_md,
        source_yml=source_yml,
        text_hash=text_hash,
    )


# ---------- knowledge-base traversal ----------


def chunk_knowledge_base(project_root: Path) -> list[Chunk]:
    """Walk ``<project_root>/knowledge-base/{5 categories}/*.md`` and
    chunk every file. Missing dirs / files are silently tolerated
    (consistent with the rest of codemap's "missing inputs degrade
    gracefully" stance)."""
    kb_root = project_root / "knowledge-base"
    if not kb_root.is_dir():
        return []
    out: list[Chunk] = []
    for category in KNOWLEDGE_CATEGORIES:
        cat_dir = kb_root / category
        if not cat_dir.is_dir():
            continue
        for md_file in sorted(cat_dir.glob("*.md")):
            try:
                md_text = md_file.read_text(encoding="utf-8")
            except OSError:
                continue
            knowledge_id = md_file.stem
            source_md = str(md_file.relative_to(project_root))
            source_yml = f".ai-memory/knowledge/{category}/{knowledge_id}.yml"
            out.extend(
                chunk_markdown(
                    md_text,
                    knowledge_id=knowledge_id,
                    category=category,
                    source_md=source_md,
                    source_yml=source_yml,
                )
            )
    return out
