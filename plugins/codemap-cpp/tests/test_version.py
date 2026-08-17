from importlib.metadata import version

from codemap_cpp import CppIndexer, __version__


def test_reported_version_matches_distribution() -> None:
    assert __version__ == version("codemap-cpp")
    assert CppIndexer.version == __version__
