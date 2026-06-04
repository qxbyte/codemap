"""JSP top-level construct extractor.

``tree-sitter-jsp`` does not exist on PyPI. This module locates the
JSP-specific constructs that matter for indexing:

* ``<%@ page import="..." %>`` — type imports (one or more comma-separated)
* ``<%@ include file="..." %>`` — server-side file inclusion
* ``<%! ... %>`` — declaration blocks (Java member declarations:
  fields, methods, classes that live at the *generated servlet* scope)
* ``<% ... %>`` — scriptlets (Java statements that live at servlet
  ``_jspService`` scope; locals here are private to one request and we
  intentionally do not surface them as symbols)
* ``<form action="..." method="...">`` — HTML form submissions, useful
  for the ``http_route`` bridge to link the page to a server controller
* ``<a href="...">`` — links to other pages or actions, same purpose

Anything else (`<c:forEach>`, EL `${...}`, custom tags) is ignored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# JSP directive: <%@ page ... %> / <%@ include ... %> / <%@ taglib ... %>
_DIRECTIVE_RE = re.compile(
    rb"<%@\s*(?P<name>\w+)\s+(?P<body>[^%]*?)%>",
    re.DOTALL,
)

# Declarations: <%! ... %>
_DECLARATION_RE = re.compile(rb"<%!\s*(?P<body>.*?)%>", re.DOTALL)

# Scriptlets: <% ... %>   — excludes <%! ... %> and <%@ ... %> directives,
# captured separately above. We use a negative-lookahead on `!` and `@`.
_SCRIPTLET_RE = re.compile(rb"<%(?![@!])\s*(?P<body>.*?)%>", re.DOTALL)

# HTML form action / link href (case-insensitive). These let the
# http_route bridge match a JSP page to its server-side controller.
_FORM_ACTION_RE = re.compile(
    rb"""<form\b[^>]*?\baction\s*=\s*(?P<q>["'])(?P<url>[^"']+)(?P=q)[^>]*?>""",
    re.IGNORECASE,
)
_FORM_METHOD_RE = re.compile(
    rb"""<form\b[^>]*?\bmethod\s*=\s*(?P<q>["'])(?P<method>[^"']+)(?P=q)""",
    re.IGNORECASE,
)
_A_HREF_RE = re.compile(
    rb"""<a\b[^>]*?\bhref\s*=\s*(?P<q>["'])(?P<url>[^"']+)(?P=q)""",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class JspImport:
    """One ``<%@ page import="..." %>`` entry. Java FQCN."""

    fqcn: str
    line: int


@dataclass(frozen=True, slots=True)
class JspInclude:
    """One ``<%@ include file="..." %>`` directive."""

    path: str
    line: int


@dataclass(frozen=True, slots=True)
class JspDeclaration:
    """One ``<%! ... %>`` block — Java member declarations."""

    content: bytes
    content_start_offset: int
    content_start_line: int


@dataclass(frozen=True, slots=True)
class JspScriptlet:
    """One ``<% ... %>`` block — Java statements in _jspService."""

    content: bytes
    content_start_offset: int
    content_start_line: int


@dataclass(frozen=True, slots=True)
class JspFormAction:
    """One ``<form action="..." method="...">``."""

    method: str
    url: str
    line: int


@dataclass(frozen=True, slots=True)
class JspLink:
    """One ``<a href="...">``."""

    url: str
    line: int


@dataclass(frozen=True, slots=True)
class JspExtract:
    """All JSP-relevant constructs found in one file."""

    imports: list[JspImport]
    includes: list[JspInclude]
    declarations: list[JspDeclaration]
    scriptlets: list[JspScriptlet]
    form_actions: list[JspFormAction]
    links: list[JspLink]


def extract(source: bytes) -> JspExtract:
    """Scan a JSP file's bytes once and return everything we care about."""
    return JspExtract(
        imports=_extract_imports(source),
        includes=_extract_includes(source),
        declarations=_extract_declarations(source),
        scriptlets=_extract_scriptlets(source),
        form_actions=_extract_form_actions(source),
        links=_extract_links(source),
    )


# ---------------------------------------------------------------------------
# Implementation details
# ---------------------------------------------------------------------------


def _line_of(source: bytes, offset: int) -> int:
    return source[:offset].count(b"\n") + 1


def _extract_imports(source: bytes) -> list[JspImport]:
    out: list[JspImport] = []
    for m in _DIRECTIVE_RE.finditer(source):
        name = m.group("name").decode("ascii", errors="replace").lower()
        if name != "page":
            continue
        body = m.group("body").decode("utf-8", errors="replace")
        for attr_value in _attr_values(body, "import"):
            # `import="java.util.List, java.util.Map"` → 2 FQCNs
            for fqcn in (s.strip() for s in attr_value.split(",")):
                if fqcn:
                    out.append(JspImport(fqcn=fqcn, line=_line_of(source, m.start())))
    return out


def _extract_includes(source: bytes) -> list[JspInclude]:
    out: list[JspInclude] = []
    for m in _DIRECTIVE_RE.finditer(source):
        name = m.group("name").decode("ascii", errors="replace").lower()
        if name != "include":
            continue
        body = m.group("body").decode("utf-8", errors="replace")
        for attr_value in _attr_values(body, "file"):
            if attr_value:
                out.append(JspInclude(path=attr_value, line=_line_of(source, m.start())))
    return out


def _extract_declarations(source: bytes) -> list[JspDeclaration]:
    out: list[JspDeclaration] = []
    for m in _DECLARATION_RE.finditer(source):
        body = m.group("body")
        content_start = m.start("body")
        out.append(
            JspDeclaration(
                content=body,
                content_start_offset=content_start,
                content_start_line=_line_of(source, content_start),
            )
        )
    return out


def _extract_scriptlets(source: bytes) -> list[JspScriptlet]:
    out: list[JspScriptlet] = []
    for m in _SCRIPTLET_RE.finditer(source):
        body = m.group("body")
        content_start = m.start("body")
        out.append(
            JspScriptlet(
                content=body,
                content_start_offset=content_start,
                content_start_line=_line_of(source, content_start),
            )
        )
    return out


def _extract_form_actions(source: bytes) -> list[JspFormAction]:
    out: list[JspFormAction] = []
    for m in _FORM_ACTION_RE.finditer(source):
        url = m.group("url").decode("utf-8", errors="replace")
        method_match = _FORM_METHOD_RE.search(m.group(0))
        method = (
            method_match.group("method").decode("ascii", errors="replace").upper()
            if method_match is not None
            else "GET"
        )
        out.append(JspFormAction(method=method, url=url, line=_line_of(source, m.start())))
    return out


def _extract_links(source: bytes) -> list[JspLink]:
    out: list[JspLink] = []
    for m in _A_HREF_RE.finditer(source):
        url = m.group("url").decode("utf-8", errors="replace")
        # Skip pure anchors / fragments / javascript: pseudo-protocol.
        if url.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        out.append(JspLink(url=url, line=_line_of(source, m.start())))
    return out


def _attr_values(body: str, attr_name: str) -> list[str]:
    """Pick attribute values from a directive body, e.g.

    ``import="java.util.List" contentType="text/html"`` →
    ``_attr_values(body, "import")`` returns ``["java.util.List"]``.
    """
    pattern = rf"""\b{re.escape(attr_name)}\s*=\s*(?P<q>["'])(?P<value>[^"']*)(?P=q)"""
    return [m.group("value") for m in re.finditer(pattern, body)]
