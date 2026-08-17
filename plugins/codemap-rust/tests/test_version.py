from importlib.metadata import version

from codemap_rust import RustIndexer, __version__


def test_reported_version_matches_distribution() -> None:
    assert __version__ == version("codemap-rust")
    assert RustIndexer.version == __version__
