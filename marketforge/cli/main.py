# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""
Command-line interface.

    marketforge generate -o ./data --from 2024-01-01 --to 2025-01-01 --instruments EURUSD --seed 42
    marketforge extend ./data --days 30
    marketforge list-instruments --market forex
    marketforge validate --input ./data/forex/EURUSD_m1.csv --market forex
"""

from __future__ import annotations

from typing import Any

import click

from marketforge import __version__
from marketforge.cli.commands.calibrate import calibrate
from marketforge.cli.commands.extend import extend
from marketforge.cli.commands.generate import generate
from marketforge.cli.commands.info import info
from marketforge.cli.commands.list_instruments import list_instruments
from marketforge.cli.commands.validate import validate
from marketforge.cli.commands.verify import verify


class _Group(click.Group):
    """
    Prints errors as one line unless ``--debug`` is given.

    A mistake in what the user asked for (an unknown instrument, a bad date, a
    directory that is not a dataset) is explained and nothing more. Only an
    error MarketForge did not expect points to ``--debug``.
    """

    def invoke(self, ctx: click.Context) -> Any:
        try:
            return super().invoke(ctx)
        except (click.ClickException, click.exceptions.Exit, click.exceptions.Abort, SystemExit):
            raise
        except Exception as e:
            if ctx.params.get("debug"):
                raise
            click.secho(f"Error: {e}", fg="red", err=True)
            if not isinstance(e, (ValueError, OSError)):
                click.echo("Run again with --debug for the full traceback.", err=True)
            ctx.exit(1)


@click.group(cls=_Group, context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--debug", is_flag=True, help="Show full tracebacks on errors.")
@click.version_option(version=__version__, prog_name="marketforge")
def cli(debug: bool) -> None:
    """MarketForge: realistic synthetic OHLCV data for crypto, forex and stocks."""


cli.add_command(generate)
cli.add_command(extend)
cli.add_command(info)
cli.add_command(calibrate)
cli.add_command(list_instruments)
cli.add_command(validate)
cli.add_command(verify)


def main() -> None:
    """Console-script entry point."""
    cli()
