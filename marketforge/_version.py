# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""The installed version of MarketForge, and the revision of its model."""

from importlib import metadata

try:
    # pyproject.toml is the single source of truth for the version.
    __version__ = metadata.version("marketforge")
except metadata.PackageNotFoundError:  # pragma: no cover - uninstalled checkout
    __version__ = "0.0.0+unknown"

# The generation of the model's output (ADR 0011). Increment it, once per
# release, in any release that changes the candles an existing seed
# produces, and list the change under "Output changes" in CHANGELOG.md.
# `extend` only continues datasets written with the same revision.
MODEL_REVISION = 2
