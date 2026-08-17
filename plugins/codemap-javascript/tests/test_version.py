from importlib.metadata import version

from codemap_javascript import JavaScriptIndexer, __version__


def test_reported_version_matches_distribution() -> None:
    assert __version__ == version("codemap-javascript")
    assert JavaScriptIndexer.version == __version__
