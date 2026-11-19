"""A strategy that fills at the quote, on stocks with real NYSE sessions.

Synthetic data with sessions, holidays, overnight gaps and a bid-ask spread
exercises what breaks backtesters: entries at the open after a gap, no
candles on holidays, and the cost of crossing the spread.
"""

import numpy as np

import marketforge as mf

data = mf.generate(
    "AAPL",
    start="2024-01-01",
    end="2024-07-01",
    seed=3,
    timeframes="m30",
    include_bid_ask=True,
)
bars = data["AAPL"]["m30"]
fast, slow = bars["close"].rolling(8).mean(), bars["close"].rolling(32).mean()
signal = (fast > slow).astype(int).shift(1).fillna(0)  # act on the next bar: no look-ahead

cash, shares, trades = 10_000.0, 0, 0
for (_, bar), want in zip(bars.iterrows(), signal, strict=True):
    if want and not shares:
        shares = int(cash // bar["ask"])  # buy at the ask
        cash -= shares * bar["ask"]
        trades += 1
    elif not want and shares:
        cash += shares * bar["bid"]  # sell at the bid
        shares = 0
        trades += 1
equity = cash + shares * bars["bid"].iloc[-1]
days = np.unique(bars.index.tz_convert("America/New_York").date).size
print(f"{days} trading days, {trades} fills, final equity {equity:,.2f}")
print("Remember: this proves the backtest runs, not that the strategy works.")
