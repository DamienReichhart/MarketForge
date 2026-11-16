---
title: Validation
description: "The stylized facts every MarketForge instrument is checked against, the bands measured on real data, and how to validate your own files."
---

Realism is not a claim in MarketForge, it is a test. The [validation bands are the realism contract](../../adr/0006-validation-bands-are-the-realism-contract/): a change that pushes any instrument outside them fails CI.

```bash
marketforge validate --input ./data/crypto/BTCUSD_m1.csv
python scripts/benchmark_realism.py --seeds 123,7 --days 14   # every instrument (from a source checkout)
```

```python
report = mf.validate(data["BTCUSD"]["m1"], "crypto")
print(report.passed)
print(report.summary())
```

```
Validation report (crypto): PASS
  ok   excess_kurtosis = 41.2343  (expected 0 to 1996.5)
  ok   vol_clustering = 0.3463  (expected at least 0.064)
  ok   leverage = -0.0771  (expected at most 0.1139)
  ok   long_memory = 0.2661  (expected at least -0.2135)
  ok   range_efficiency = 1.5711  (expected 1.254 to 1.996)
  ok   spread_bps = 0.0208  (expected 0.012 to 3.892)
  ok   spread_widening = 1.0936  (expected 0.904 to 1.597)
```

## What is measured

The validator takes **`m1` candles only** and refuses other timeframes: the bands describe minute returns. It measures open-to-close minute returns (overnight and weekend gaps excluded) against per-market bands:

| Statistic | Stylized fact |
| --- | --- |
| `excess_kurtosis` | **Heavy tails**: excess kurtosis in a realistic range. |
| `vol_clustering` | **Volatility clustering**: the autocorrelation of \|returns\| over the first 20 minutes is significant. |
| `long_memory` | **Long memory**: \|returns\| are still autocorrelated an hour later. |
| `leverage` | **Leverage effect**: returns are not positively correlated with next-period volatility. Looser for forex, where crosses have no natural "down". |
| `range_efficiency` | mean(high − low) / mean(\|close − open\|). A pure random walk gives 2.0; real minutes wander less inside the bar. |
| `spread_bps`, `spread_widening` | When the file has a `spread` column: the median spread in basis points is realistic, and the most turbulent minutes are about as much wider than the median as in real quotes. |

## Noise allowances

Heavy tails, long memory and the leverage effect allow two standard errors of sampling noise, **estimated from the sample itself**. The textbook formulas assume independent normal data and are 2.5 times too small on minute returns, which made sound two-week samples fail by chance. See [ADR 0010](../../adr/0010-noise-allowances-use-the-samples-own-standard-errors/).

## Where the bands come from

The bands are anchored on the same statistics measured on real `m1` data.

- **Crypto** is anchored on Binance 1-minute klines of seven coins (BTC, ETH, SOL, XRP, DOGE, TRX, LINK; February 2024), and its spread bands on Binance USDT-futures best bid/ask for the same coins. Generated crypto data falls inside the measured real range for \|r\| autocorrelation from 15 minutes to 1 day, clustering, leverage, range efficiency, volume dynamics and spread.
- **Forex and stocks** use **provisional** bands, for the spread too, until real reference data is measured for them, and their reports say so. No free source of forex or stock quotes was reachable when they were calibrated.

With two-week windows and three seeds, all 624 instrument checks pass. Across 30 seeds, 6237 of 6240 pass; the three failures are stock fortnights in which volatility shows no memory at all, which is what that check is there to flag.

## Validate your own data

The validator works on any CSV or Parquet file with `timestamp, open, high, low, close` columns, so you can check real data, another generator, or your own model's output against the same bands:

```bash
marketforge validate --input ./my_eurusd_m1.csv --market forex
```

To measure a real dataset's statistics, or to help anchor the provisional forex and stock bands, use the measurement script from a source checkout:

```bash
python scripts/measure_real_data.py --name EURUSD ./my_eurusd_m1/*.csv   # timestamp,open,high,low,close[,volume,spread]
```

Contributions of measurements on licensable forex or stock data are welcome. See [Contributing](../../contributing/).
