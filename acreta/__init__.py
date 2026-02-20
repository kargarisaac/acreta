"""Acreta package bootstrap: logging initialization and version export."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from acreta.config.logging import configure_logging

configure_logging()


try:
    __version__ = version("acreta")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["__version__"]
