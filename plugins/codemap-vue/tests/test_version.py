from importlib.metadata import version

from codemap_vue import VueIndexer, __version__


def test_reported_version_matches_distribution() -> None:
    assert __version__ == version("codemap-vue")
    assert VueIndexer.version == __version__
