# Derive forex crosses from anchor pairs

Simulating all 81 forex instruments independently produced EURJPY ≠ EURUSD × USDJPY, i.e. free triangular arbitrage that no real market allows. We now pick one anchor pair per code (a spanning tree rooted at USD, preferring pairs quoted against USD) and simulate only those; every cross's log price is an exact signed sum of anchor log prices. Crosses therefore ignore their own catalog start price and volatility: both emerge from the anchors and their correlations.

## Consequences

- Anomalies (spikes, flash crashes) are applied per instrument after derivation and do break triangular consistency; that is the point of an anomaly.
- A user-defined forex instrument whose codes are already connected becomes a cross; its configured volatility is ignored.
