---
title: Backtesting
description: "Test a backtesting engine or trading system against data that behaves like a real feed: calendars, gaps, spreads and aligned multi-asset panels."
---

Most backtester bugs are not in the strategy but in the plumbing: a session that starts at the wrong hour, a forward-filled weekend, a fill at a price that never existed, two instruments misaligned by a minute. Clean CSVs from a single 24/7 market hide all of them. MarketForge produces data with the awkward properties of real feeds, on demand and reproducibly, so you can find those bugs before they cost money.

## What to test your engine against

### Calendars and closures

- **Stocks** trade the NYSE session, 09:30 to 16:00 New York time, DST-aware, and skip NYSE holidays and early closes.
- **Forex** trades from Sunday 17:00 to Friday 17:00 New York time.
- **Crypto** never closes.

No candle is printed while a market is closed. An engine that assumes a candle every minute, or every day, breaks here. Daily candles start where the market's day does: 00:00 UTC for crypto, 17:00 New York for forex, the 09:30 open for stocks. See [Markets & calendars](../../reference/markets/).

### Gaps

The first candle after a closure opens away from the previous close, because the price moved while the market was closed. Stocks build up roughly 30% of a session's variance overnight; a typical EURUSD weekend gap is about 10 pips. Check that stop orders gap through their level instead of filling at it.

### Mid prices and the spread

Candle prices are **mid prices**. With `--with-spread`, each candle carries the mean quoted bid-ask spread, so:

```text title="Bid and ask from the mid price"
bid = price - spread / 2
ask = price + spread / 2
```

The spread widens in turbulent markets, in quiet hours and at the reopen: forex spreads are about five times wider when the week opens, stock spreads four times wider at the open. A strategy that only works when it trades the mid is not a strategy. See [Bid-ask spread](../../reference/spread/).

### Multi-asset alignment

`GeneratedData.panel()` puts every instrument on the union of their candle times, with NaN where a market was closed, never forward-filled. Mixing AAPL and BTCUSD shows immediately whether your engine handles instruments that do not trade at the same times.

Forex crosses are derived from anchor pairs, so `EURJPY == EURUSD * USDJPY` at every minute, to within the tick each is quoted on: a triangular-arbitrage strategy should find nothing once it pays the spread. If it does, the engine has a look-ahead or alignment bug.

### Higher timeframes

Higher timeframes are aggregated from the same minutes and aligned to each market's clock (forex H4 candles start at 17:00, 21:00, 01:00, ... New York). A partial first or last candle is never published. Compare your engine's own resampling against MarketForge's files to catch off-by-one bucketing.

## Known answers

Synthetic data lets you build tests with a known answer:

- **Zero-edge baseline.** Generate a market with `drift = 0` in an [override file](../../guides/custom-instruments/) and run a random-entry strategy across many seeds. Its mean P&L before costs should be zero, and after costs should be minus the spread you paid. Anything else is a bug in fills or accounting.
- **Look-ahead detector.** A strategy that peeks one candle ahead makes money on every seed. Run your real strategy across 50 seeds: consistent profits on data with no edge are a red flag.
- **Regression tests.** Fix a seed and a version, store the expected trades, and assert them in CI. The data will be bit-for-bit identical on the next run with the same version and platform.

```bash
# A fixed fixture for the engine's test suite: one month, three markets, small
marketforge generate -o tests/fixtures/market --from 2024-03-01 --days 31 \
    -i AAPL,EURUSD,BTCUSD -t m5,H1,D1 --with-spread --seed 7
```

## From one equity curve to a distribution

A backtest on real data gives you one equity curve. Run the same strategy over many seeds to see the distribution of outcomes it produces, and see [Stress testing](../stress-testing/) for crashes and tail events.

## Recipes for your engine

MarketForge's frames are pandas DataFrames on a UTC index, so most engines take them with a rename. Each recipe below runs in CI against the released package and the engine's current version: if an engine changes its API, the page is fixed before you copy it. A converter that writes each engine's own file layout is [tracked as an issue](https://github.com/DamienReichhart/marketforge/issues/27).

### backtrader

`PandasData` reads `open`, `high`, `low`, `close` and `volume` by name; it wants naive times, so drop the time zone (the times stay UTC).

```python
import backtrader as bt
import marketforge as mf

frame = mf.generate("AAPL", start="2024-01-02", days=30, seed=1, timeframes="m5")["AAPL"]["m5"]
feed = bt.feeds.PandasData(dataname=frame.tz_convert(None))


class SmaCross(bt.Strategy):
    def __init__(self):
        self.cross = bt.ind.CrossOver(bt.ind.SMA(period=10), bt.ind.SMA(period=30))

    def next(self):
        if self.cross > 0:
            self.buy()
        elif self.cross < 0:
            self.close()


cerebro = bt.Cerebro()
cerebro.adddata(feed)
cerebro.addstrategy(SmaCross)
cerebro.run()
print(round(cerebro.broker.getvalue(), 2))
```

### backtesting.py

It wants capitalised column names.

```python
from backtesting import Backtest, Strategy
from backtesting.lib import crossover
from backtesting.test import SMA

frame = mf.generate("ETHUSD", start="2024-01-01", days=30, seed=2, timeframes="H1")["ETHUSD"]["H1"]
ohlcv = frame.tz_convert(None).rename(columns=str.capitalize)  # Open, High, Low, Close, Volume


class Crossing(Strategy):
    def init(self):
        self.fast = self.I(SMA, self.data.Close, 10)
        self.slow = self.I(SMA, self.data.Close, 30)

    def next(self):
        if crossover(self.fast, self.slow):
            self.buy()
        elif crossover(self.slow, self.fast):
            self.position.close()


stats = Backtest(ohlcv, Crossing, cash=100_000, commission=0.0005).run()
print(stats["Return [%]"])
```

### vectorbt

`panel()` is already the wide frame vectorbt broadcasts over: one column per instrument.

```python
import vectorbt as vbt

data = mf.generate("BTCUSD,ETHUSD,SOLUSD", start="2024-01-01", days=30, seed=3, timeframes="H1")
close = data.panel("close", "H1")
fast, slow = vbt.MA.run(close, 10), vbt.MA.run(close, 30)
portfolio = vbt.Portfolio.from_signals(
    close, fast.ma_crossed_above(slow), fast.ma_crossed_below(slow), fees=0.0005, freq="1h"
)
print(portfolio.total_return())
```

### Nautilus Trader

Nautilus stamps a bar at its close and takes prices and sizes at the instrument's precision. Build the bars directly: its `BarDataWrangler` writes into the frame's buffers, which pandas 3 makes read-only.

```python
from decimal import Decimal

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.examples.strategies.ema_cross import EMACross, EMACrossConfig
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money
from nautilus_trader.test_kit.providers import TestInstrumentProvider

instrument = TestInstrumentProvider.default_fx_ccy("EUR/USD")
bar_type = BarType.from_str(f"{instrument.id}-1-MINUTE-MID-EXTERNAL")
m1 = mf.generate("EURUSD", start="2024-01-08", days=5, seed=5, timeframes="m1")["EURUSD"]["m1"]
price, size = instrument.make_price, instrument.make_qty
closes = (m1.index.as_unit("ns").asi8 + 60_000_000_000).tolist()  # a bar is stamped at its close
bars = [
    Bar(bar_type, price(o), price(h), price(l), price(c), size(v), ts, ts)
    for o, h, l, c, v, ts in zip(*(m1[k] for k in ("open", "high", "low", "close", "volume")), closes)
]

engine = BacktestEngine(BacktestEngineConfig(logging=LoggingConfig(bypass_logging=True)))
engine.add_venue(
    Venue("SIM"), OmsType.HEDGING, AccountType.MARGIN, base_currency=USD,
    starting_balances=[Money(100_000, USD)],
)
engine.add_instrument(instrument)
engine.add_data(bars)
engine.add_strategy(EMACross(EMACrossConfig(
    instrument_id=instrument.id, bar_type=bar_type, trade_size=Decimal(10_000),
    fast_ema_period=10, slow_ema_period=30,
)))
engine.run()
print(len(engine.trader.generate_order_fills_report()), "fills")
engine.dispose()
```

### freqtrade

`marketforge export freqtrade` writes a dataset as freqtrade's data directory expects it: one Feather file per pair and timeframe, `{BASE}_{QUOTE}-{timeframe}.feather` with a `date` column in UTC. `--quote USDT` names the coins' dollar as an exchange that lists them against USDT does.

```bash
marketforge generate -o ./coins -i BTCUSD,ETHUSD --from 2024-01-01 --days 30 --seed 4 -t m5,H1,D1
marketforge export freqtrade ./coins user_data/data/binance --quote USDT
```

Then `freqtrade backtesting --timeframe 1h --pairs BTC/USDT ETH/USDT ...` finds the candles. Timeframes freqtrade does not have (`m2`, `m10`, `m20`, `H3`) are skipped and listed. In Python, `mf.export("freqtrade", "coins", "user_data/data/binance", quote="USDT")`.

### LEAN (QuantConnect)

`marketforge export lean` turns a dataset's `m1` candles into LEAN's data folder: zipped minute files per day, and hour and daily files per ticker. Stocks go under `equity/usa` (New York time, prices in ten-thousandths, with a map and a factor file), coins under `crypto/coinbase`, currency pairs under `forex/oanda`, and gold, the index and the oil CFDs under `cfd/oanda` (UTC). Forex and CFDs have quote bars: generate with `--with-bid-ask` (or `--with-spread`) so they hold the spread.

```bash
marketforge generate -o ./mixed -i AAPL,EURUSD,BTCUSD --from 2024-03-04 --days 6 --seed 7 -t m1 --with-bid-ask
marketforge export lean ./mixed ./lean-data
```

Point LEAN's `data-folder` at `./lean-data`, next to its own `market-hours` and `symbol-properties` folders, and `AddEquity("AAPL")`, `AddForex("EURUSD", market=Market.Oanda)` and `AddCrypto("BTCUSD", market=Market.Coinbase)` read the candles. CI runs an algorithm on such an export in LEAN's own Docker image, and a freqtrade backtest on a freqtrade export, on every change.
