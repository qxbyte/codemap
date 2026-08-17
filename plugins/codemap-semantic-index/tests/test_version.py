from importlib.metadata import version

from codemap_semantic_index import __version__


def test_reported_version_matches_distribution() -> None:
    assert __version__ == version("codemap-semantic-index")
