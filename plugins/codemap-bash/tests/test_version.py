from importlib.metadata import version

from codemap_bash import BashIndexer, __version__


def test_reported_version_matches_distribution() -> None:
    assert __version__ == version("codemap-bash")
    assert BashIndexer.version == __version__
