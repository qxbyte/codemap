from importlib.metadata import version

from codemap_swift import SwiftIndexer, __version__


def test_reported_version_matches_distribution() -> None:
    assert __version__ == version("codemap-swift")
    assert SwiftIndexer.version == __version__
