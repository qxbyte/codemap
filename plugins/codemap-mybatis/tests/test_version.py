from importlib.metadata import version

from codemap_mybatis import MyBatisIndexer, __version__
from codemap_mybatis.link import MyBatisLinkBridge


def test_reported_version_matches_distribution() -> None:
    assert __version__ == version("codemap-mybatis")
    assert MyBatisIndexer.version == __version__
    assert MyBatisLinkBridge.version == __version__
