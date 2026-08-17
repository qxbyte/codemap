from importlib.metadata import version

from codemap_scala import ScalaIndexer, __version__


def test_reported_version_matches_distribution() -> None:
    assert __version__ == version("codemap-scala")
    assert ScalaIndexer.version == __version__
