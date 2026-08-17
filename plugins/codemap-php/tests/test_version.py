from importlib.metadata import version

from codemap_php import PhpIndexer, __version__


def test_reported_version_matches_distribution() -> None:
    assert __version__ == version("codemap-php")
    assert PhpIndexer.version == __version__
