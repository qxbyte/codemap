from importlib.metadata import version

from codemap_aimemory import AiMemoryEmitter, __version__


def test_reported_version_matches_distribution() -> None:
    assert __version__ == version("codemap-aimemory")
    assert AiMemoryEmitter.version == __version__
