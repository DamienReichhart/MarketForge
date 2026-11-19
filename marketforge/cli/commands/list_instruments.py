# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""``marketforge list-instruments``."""

from __future__ import annotations

import click

from marketforge.api.catalog import instruments
from marketforge.cli.renamed import renamed_option
from marketforge.domain.markets import MarketType


@click.command("list-instruments")
@click.option(
    "--markets",
    "-m",
    metavar="LIST",
    help="Comma-separated markets: crypto, forex, stocks, or all (the default).",
)
@renamed_option("--market", "--markets")
@click.option(
    "--search",
    "-s",
    metavar="TEXT",
    help="Only the symbols that contain TEXT, in any letter case (e.g. EUR).",
)
@click.option(
    "--overrides",
    "overrides",
    type=click.Path(exists=True, dir_okay=False),
    help="Override file (TOML) to apply first.",
)
@renamed_option("--config", "--overrides")
@click.option("--json", "as_json", is_flag=True, help="Print the instruments as JSON.")
def list_instruments(
    markets: str | None, search: str | None, overrides: str | None, as_json: bool
) -> None:
    """List available instruments with their start price, volatility, drift and volume."""
    table = instruments(markets, overrides=overrides)
    if search:
        table = table[table.index.str.contains(search.strip().upper(), regex=False)]
        if table.empty:
            raise click.ClickException(f"No instrument contains {search!r}")
    if as_json:
        rows = table.reset_index().rename(columns={"index": "symbol"})
        click.echo(rows.to_json(orient="records", indent=2))
        return
    for name, rows in table.groupby("market", sort=False):
        click.secho(f"\n{name} ({len(rows)} instruments)", bold=True)
        click.echo(f"  {'SYMBOL':<10}{'START':>14}{'VOL':>8}{'DRIFT':>8}{'VOLUME':>12}  NOTE")
        for symbol, row in rows.iterrows():
            note = (
                "" if name != MarketType.FOREX else "cross (derived)" if row.derived else "anchor"
            )
            click.echo(
                f"  {symbol:<10}{row.start_price:>14,.4f}{row.volatility:>8.3f}"
                f"{row.drift:>8.3f}{row.volume_base:>12,.1f}  {note}"
            )
