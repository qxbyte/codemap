from importlib.metadata import version

from codemap_csharp import CSharpIndexer, __version__


def test_reported_version_matches_distribution() -> None:
    assert __version__ == version("codemap-csharp")
    assert CSharpIndexer.version == __version__
