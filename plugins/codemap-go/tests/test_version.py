from importlib.metadata import version

from codemap_go import GoIndexer, __version__


def test_reported_version_matches_distribution() -> None:
    assert __version__ == version("codemap-go")
    assert GoIndexer.version == __version__
