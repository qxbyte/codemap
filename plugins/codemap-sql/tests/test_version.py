from importlib.metadata import version

from codemap_sql import SqlIndexer, __version__


def test_reported_version_matches_distribution() -> None:
    assert __version__ == version("codemap-sql")
    assert SqlIndexer.version == __version__
