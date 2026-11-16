# Stay in Python and compile the hot loops with Numba

Generation was slow (≈10 s per asset-year of m1) because three per-minute recursions (regime Markov chain, GJR-GARCH, log-volume AR(1)) ran as plain Python loops, which also made threading useless. We considered a Rust or C++ rewrite and rejected it: the cost lives in a handful of recursions, not in the language, and a rewrite would discard the validation harness and test suite. Those recursions are now Numba-compiled kernels; everything else stays vectorised NumPy.
