# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""
Command-line options that 5.0 renamed: the old spelling fails with a pointer.

Kept for the 5.x series only; MarketForge 6.0 deletes this module and every
``renamed_option`` (see AGENTS.md).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import click


def renamed_option(old: str, instead: str, *, flag: bool = False) -> Callable[[Any], Any]:
    """A hidden ``old`` option whose use is an error saying what to write ``instead``."""

    def refuse(ctx: click.Context, param: click.Parameter, value: Any) -> None:
        if value not in (None, False, ()):
            raise click.UsageError(f"MarketForge 5.0 replaced {old}: use {instead}.", ctx=ctx)

    return click.option(
        old,
        f"_renamed_{old.lstrip('-').replace('-', '_')}",
        is_flag=flag,
        hidden=True,
        expose_value=False,
        callback=refuse,
    )
