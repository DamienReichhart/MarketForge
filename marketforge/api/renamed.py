# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""
Names that 5.0 renamed: using an old one fails with a pointer to the new one.

Kept for the 5.x series only. MarketForge 6.0 deletes this module, the
``@renamed_arguments`` decorators and the hidden command-line options built
with :func:`marketforge.cli.renamed.renamed_option` (see AGENTS.md).
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

# Old keyword argument -> new one, in every public function that took it.
RENAMED_ARGUMENTS = {
    "fmt": "format",
    "include_regime": "with_regime",
    "include_spread": "with_spread",
    "include_bid_ask": "with_bid_ask",
}


def renamed_arguments[F: Callable[..., Any]](func: F) -> F:
    """Make an old keyword argument a ``TypeError`` that names its new spelling."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        for old in kwargs.keys() & RENAMED_ARGUMENTS.keys():
            raise TypeError(
                f"{func.__name__}() got {old}=, which MarketForge 5.0 renamed "
                f"{RENAMED_ARGUMENTS[old]}="
            )
        return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]
