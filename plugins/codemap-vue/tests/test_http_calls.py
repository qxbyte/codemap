"""Plan 4 Task 1: VueIndexer captures axios / fetch HTTP calls.

Records land on the enclosing function/method symbol's
``extra["http_calls"]`` as a list of ``{"method", "url", "confidence"}``
dicts so the existing :class:`HttpRouteBridge` can match them against
server-side ``http_route`` metadata.
"""

from __future__ import annotations

import textwrap
from pathlib import Path, PurePosixPath

from codemap_vue.indexer import VueIndexer

from codemap.core.models import IndexResult
from codemap.indexers.base import IndexContext


def _index(source: str, *, rel: str = "src/X.vue") -> IndexResult:
    code = textwrap.dedent(source).lstrip("\n")
    return VueIndexer().index_file(
        Path(f"/tmp/{rel}"),
        code.encode("utf-8"),
        IndexContext(
            project_root=Path("/tmp"),
            relative_path=PurePosixPath(rel),
            language="vue",
        ),
    )


def _calls_in(r: IndexResult) -> list[dict]:
    return [c for s in r.symbols for c in s.extra.get("http_calls", [])]


# ----- axios verbs (this.$axios) -----


def test_this_axios_post_recorded() -> None:
    r = _index(
        """
        <script>
        export default { methods: { load() { this.$axios.post('/api/order/price', {}) } } }
        </script>
        """
    )
    assert {"method": "POST", "url": "/api/order/price", "confidence": "medium"} in _calls_in(r)


def test_this_axios_get_recorded() -> None:
    r = _index(
        """
        <script>
        export default { methods: { load() { this.$axios.get('/api/list') } } }
        </script>
        """
    )
    assert {"method": "GET", "url": "/api/list", "confidence": "medium"} in _calls_in(r)


def test_axios_put_recorded() -> None:
    r = _index(
        """
        <script>
        function update() { axios.put('/api/u', {a: 1}) }
        </script>
        """
    )
    assert {"method": "PUT", "url": "/api/u", "confidence": "medium"} in _calls_in(r)


def test_axios_delete_recorded() -> None:
    r = _index(
        """
        <script>
        function rm() { axios.delete('/api/r') }
        </script>
        """
    )
    assert {"method": "DELETE", "url": "/api/r", "confidence": "medium"} in _calls_in(r)


def test_axios_patch_recorded() -> None:
    r = _index(
        """
        <script>
        function patch() { axios.patch('/api/p', {}) }
        </script>
        """
    )
    assert {"method": "PATCH", "url": "/api/p", "confidence": "medium"} in _calls_in(r)


# ----- fetch -----


def test_fetch_default_get_recorded() -> None:
    r = _index(
        """
        <script>
        function load() { fetch('/api/list') }
        </script>
        """
    )
    assert {"method": "GET", "url": "/api/list", "confidence": "medium"} in _calls_in(r)


# ----- url confidence grading -----


def test_template_url_marked_low() -> None:
    r = _index(
        """
        <script>
        function load() { axios.get(`/api/u/${id}`) }
        </script>
        """
    )
    calls = _calls_in(r)
    assert any(c["confidence"] == "low" and "api" in c["url"] for c in calls)


def test_concatenated_url_marked_low() -> None:
    r = _index(
        """
        <script>
        function load() { axios.get('/api/u/' + id) }
        </script>
        """
    )
    calls = _calls_in(r)
    assert any(c["confidence"] == "low" for c in calls)


# ----- attribution to enclosing function -----


def test_call_attached_to_enclosing_method() -> None:
    r = _index(
        """
        <script>
        export default { methods: {
            load()  { axios.get('/a') },
            other() { axios.post('/b', {}) },
        }}
        </script>
        """
    )
    methods = {s.id.descriptors[-1].name: s for s in r.symbols if s.kind == "method"}
    load_calls = methods["load"].extra.get("http_calls", [])
    other_calls = methods["other"].extra.get("http_calls", [])
    assert any(c["url"] == "/a" for c in load_calls)
    assert any(c["url"] == "/b" for c in other_calls)
    # cross-contamination check
    assert not any(c["url"] == "/b" for c in load_calls)


def test_no_http_call_means_no_extra_key() -> None:
    r = _index(
        """
        <script>
        export default { methods: { helper() { return 1 } } }
        </script>
        """
    )
    methods = [s for s in r.symbols if s.kind == "method"]
    assert all("http_calls" not in m.extra for m in methods)


def test_unrelated_call_is_ignored() -> None:
    r = _index(
        """
        <script>
        function f() { console.log('hello') }
        </script>
        """
    )
    assert _calls_in(r) == []
