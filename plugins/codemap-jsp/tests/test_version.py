from importlib.metadata import version

from codemap_jsp import JspIndexer, __version__


def test_reported_version_matches_distribution() -> None:
    assert __version__ == version("codemap-jsp")
    assert JspIndexer.version == __version__
