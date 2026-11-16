# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""The installed version of MarketForge."""

from importlib import metadata

try:
    # pyproject.toml is the single source of truth for the version.
    __version__ = metadata.version("marketforge")
except metadata.PackageNotFoundError:  # pragma: no cover - uninstalled checkout
    __version__ = "0.0.0+unknown"
