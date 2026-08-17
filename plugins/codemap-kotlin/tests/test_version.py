from importlib.metadata import version

from codemap_kotlin import KotlinIndexer, __version__


def test_reported_version_matches_distribution() -> None:
    assert __version__ == version("codemap-kotlin")
    assert KotlinIndexer.version == __version__
