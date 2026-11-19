"""Helpers shared by the test modules."""

from __future__ import annotations

from marketforge.domain.bars import Bars
from marketforge.domain.time import SECONDS_PER_DAY
from marketforge.simulation.simulator import MarketSimulator


def simulate_days(sim: MarketSimulator, start: int, end: int) -> list[Bars]:
    """The m1 candles of every UTC day of [start, end) with at least one open minute."""
    days = range(start // SECONDS_PER_DAY, (end - 1) // SECONDS_PER_DAY + 1)
    return [bars for day in days if (bars := sim.simulate_day(day, start, end)) is not None]
