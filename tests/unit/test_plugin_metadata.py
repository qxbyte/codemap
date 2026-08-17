from importlib.metadata import PackageNotFoundError

import codemap.plugin_metadata as plugin_metadata


def test_package_version_reads_distribution_metadata(monkeypatch) -> None:
    monkeypatch.setattr(plugin_metadata.metadata, "version", lambda name: f"found:{name}")

    assert plugin_metadata.package_version("codemap-bash") == "found:codemap-bash"


def test_package_version_uses_source_fallback(monkeypatch) -> None:
    def missing(_name: str) -> str:
        raise PackageNotFoundError

    monkeypatch.setattr(plugin_metadata.metadata, "version", missing)

    assert plugin_metadata.package_version("codemap-bash") == "0.0.0.dev0"
