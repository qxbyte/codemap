from importlib.metadata import version

from codemap_java import JavaIndexer, __version__
from codemap_java.resolver import JavaCallResolverBridge


def test_reported_version_matches_distribution() -> None:
    assert __version__ == version("codemap-java")
    assert JavaIndexer.version == __version__
    assert JavaCallResolverBridge.version == __version__
