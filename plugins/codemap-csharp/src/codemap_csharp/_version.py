"""Installed distribution version."""

from importlib import metadata

try:
    __version__ = metadata.version("codemap-csharp")
except metadata.PackageNotFoundError:
    __version__ = "0.0.0.dev0"
