# Optimise without changing a single bit

3.0's speed was limited by Python-level waste, not by the language (ADR 0003 still holds). The worst cases were thousands of tiny CSV writes and `np.round` calls, re-concatenating the open weekly bucket every day, recomputing the whole market after the draws when one instrument was requested, and rebuilding a multi-million-step regime calibration in every simulator. 3.1 removes that waste under one rule: **for every seed, the output must stay identical, bit for bit, to 3.0's**. The rule is what lets the change ship as a minor version (ADR 0006).

What keeps a rewrite bit-identical:

- **IEEE-exact operations only in Numba.** `+ - * /`, `sqrt`, `abs`, `min`/`max` and sequential sums are correctly rounded everywhere, so a Numba kernel that evaluates them in the same order and grouping as the NumPy expression gives the same double. Kernels never use `fastmath`, so LLVM never contracts `a * b + c` into an FMA.
- **Transcendentals stay in NumPy.** NumPy's SIMD `exp`/`log` (AVX-512 here) differ from libm, and so from Numba, in the last bit on about 5% / 0.1% of inputs. Kernels prepare the arguments and NumPy applies `np.exp`/`np.log` in place.
- **NumPy internals stay NumPy.** `einsum`, BLAS products and `ufunc.reduceat` have summation orders we do not own: one einsum evaluation order does reproduce it in tests, but that order is an implementation detail that may change between NumPy releases. So they are still called with the same operands, only less often. The exception is the forex projection: every built-in instrument is a sum of at most two anchors with weights of +-1, and any order of such a sum rounds to the same double, so an exact kernel replaces the matrix product. Structures beyond that (possible through overrides) keep the matrix product.
- **Column independence makes subsets exact.** After the market-wide draws and the correlation matrix product, every operation works column by column (per factor or per instrument), so dropping unrequested columns cannot change the kept ones. Aggregation reduces each bucket over exactly the same rows; `reduceat` was checked to give the same segment sums whatever surrounds the segment.

## Consequences

- Each fused kernel is tested against the verbatim 3.0 NumPy expression (`tests/simulation/test_kernels.py`), and subset simulation against the whole market for all three projection kinds (`tests/simulation/test_simulator.py`). These tests run on every platform in CI.
- The release was also checked against 3.0 on 4,717 outputs (in-memory frames, CSV bytes, Parquet columns): every market, spikes and flash crashes, both DST transitions, holidays and early closes, mid-day starts, subsets, overrides and a three-anchor cross. The check passed with the newest dependencies and at the declared floors (Python 3.10, NumPy 2.2.0, Numba 0.61.2).
- Moving `exp`/`log` into compiled code (or into Rust) would change output on some CPUs and therefore needs a major version.
- The whole-market random draws remain the floor of single-instrument runs (about 2.5 ms per simulated forex day); removing them would change every seed.
