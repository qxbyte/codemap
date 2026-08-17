from importlib.metadata import version

from codemap_c import CIndexer, __version__


def test_reported_version_matches_distribution() -> None:
    assert __version__ == version("codemap-c")
    assert CIndexer.version == __version__
