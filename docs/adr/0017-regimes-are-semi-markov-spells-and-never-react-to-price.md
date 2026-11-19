# Regimes are semi-Markov spells and never react to price

Regimes were a per-minute Markov chain, so every spell length was geometric: its standard deviation equalled its mean (measured 0.83 to 1.0 times), and a minute was as likely as any other to end a spell. A hidden Markov model was then exactly the right model of the data, so a regime detector scored better on MarketForge than it can on real markets, which weakens the labels the package exists for.

**Decision.** A regime lasts a spell whose length is its mean (from the transition matrix, as before) times a Gamma draw of shape 2 and mean 1: a typical length, with a coefficient of variation of 0.71. When the spell ends, the next regime is drawn from the matrix's off-diagonal row, tilted towards high volatility and crashes while the macro state is stressed (ADR 0016). Regimes stay exogenous: no price, drawdown or volatility ever changes when a spell ends.

## Considered options

- **A crash hazard that rises with the drawdown.** Realistic, but the label would become a function of the path: detecting the regime would partly become detecting the drawdown, and the label would stop being an independent ground truth.

## Consequences

- Every seed's candles and labels change (model revision 2). Mean spell lengths, the time share of each regime and the trend strengths are those of the transition matrix, as before.
- The simulator's checkpoint carries the minutes left in the current spell.
