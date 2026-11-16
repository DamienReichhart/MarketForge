# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the GNU Affero General Public License v3.0 or later.
# See the LICENSE file in the project root for full license information.

"""``marketforge list-instruments``."""

from __future__ import annotations

import click

from marketforge.api.catalog import instruments
from marketforge.domain.markets import MarketType


@click.command("list-instruments")
@click.option(
    "--market", "-m", type=click.Choice([m.value for m in MarketType]), help="Only this market."
)
@click.option(
    "--config",
    "overrides",
    type=click.Path(exists=True, dir_okay=False),
    help="TOML override file to apply first.",
)
def list_instruments(market: str | None, overrides: str | None) -> None:
    """List available instruments with their start price and volatility."""
    table = instruments(market, overrides=overrides)
    for name, rows in table.groupby("market", sort=False):
        click.secho(f"\n{name} ({len(rows)} instruments)", bold=True)
        click.echo(f"  {'SYMBOL':<10}{'START':>14}{'VOL':>8}{'DRIFT':>8}  NOTE")
        for symbol, row in rows.iterrows():
            note = (
                "" if name != MarketType.FOREX else "cross (derived)" if row.derived else "anchor"
            )
            click.echo(
                f"  {symbol:<10}{row.start_price:>14,.4f}{row.volatility:>8.3f}{row.drift:>8.3f}  {note}"
            )
