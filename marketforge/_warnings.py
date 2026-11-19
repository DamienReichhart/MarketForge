# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""Where MarketForge's warnings point: at the caller's code, never at MarketForge's."""

from __future__ import annotations

from pathlib import Path

# Pass as ``warnings.warn(..., skip_file_prefixes=PACKAGE_DIRS)``: the warning
# is attributed to the first frame outside the package, however deep it is raised.
PACKAGE_DIRS = (str(Path(__file__).resolve().parent),)
