from importlib.metadata import version

from codemap_ruby import RubyIndexer, __version__


def test_reported_version_matches_distribution() -> None:
    assert __version__ == version("codemap-ruby")
    assert RubyIndexer.version == __version__
