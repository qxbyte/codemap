from importlib.metadata import version

from codemap_typescript import TypeScriptIndexer, __version__


def test_reported_version_matches_distribution() -> None:
    assert __version__ == version("codemap-typescript")
    assert TypeScriptIndexer.version == __version__
