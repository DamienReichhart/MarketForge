# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""``marketforge list-assets``."""

from __future__ import annotations

import click

from marketforge.config.loader import load_catalog
from marketforge.domain.markets import MarketType
from marketforge.simulation.spec import build_market_spec


@click.command("list-assets")
@click.option(
    "--market", "-m", type=click.Choice([m.value for m in MarketType]), help="Only this market."
)
@click.option(
    "--config",
    "overrides",
    type=click.Path(exists=True, dir_okay=False),
    help="TOML override file to apply first.",
)
def list_assets(market: str | None, overrides: str | None) -> None:
    """List available instruments with their start price and volatility."""
    catalog = load_catalog(overrides)
    for m, cfg in catalog.items():
        if market and m.value != market:
            continue
        spec = build_market_spec(cfg)
        anchors = set(spec.structure.factors)
        click.secho(f"\n{m.value} ({cfg.n_assets} instruments)", bold=True)
        click.echo(f"  {'SYMBOL':<10}{'START':>14}{'VOL':>8}{'DRIFT':>8}  NOTE")
        for s in cfg.symbols:
            a = cfg.get_asset(s)
            note = (
                ""
                if spec.structure.is_identity
                else ("anchor" if s in anchors else "cross (derived)")
            )
            click.echo(
                f"  {s:<10}{a.start_price:>14,.4f}{a.volatility:>8.3f}{a.drift:>8.3f}  {note}"
            )
