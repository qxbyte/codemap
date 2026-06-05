"""CodeMap — language-neutral code index for AI agents."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("codemap-core")
except PackageNotFoundError:
    # Fallback for running from source without installing
    __version__ = "0.0.0.dev0"

__all__ = ["__version__"]
