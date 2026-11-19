import subprocess
import sys

import numpy as np
import pytest

from marketforge.simulation.kernels import (
    ar1,
    bar_arguments,
    bridge_extremes,
    factor_paths,
    finish_bars,
    gjr_garch,
    project_signed,
    regime_chain,
)


def _cum(p):
    return np.cumsum(np.asarray(p, dtype=float), axis=1)


def test_regime_chain_matches_stationary_distribution():
    p = np.array([[0.9, 0.1], [0.3, 0.7]])
    rng = np.random.default_rng(0)
    regimes, *_ = regime_chain(
        rng.random(200_000), _cum(p), np.zeros(2), np.ones(2), 1.0, 0, 0.0, 1.0
    )
    # Stationary distribution of p is (0.75, 0.25).
    assert abs((regimes == 0).mean() - 0.75) < 0.01


def test_regime_chain_is_resumable():
    p = np.array([[0.8, 0.2], [0.4, 0.6]])
    u = np.random.default_rng(1).random(1000)
    args = (_cum(p), np.array([1.0, -1.0]), np.array([1.0, 3.0]), 0.1)
    full = regime_chain(u, *args, 0, 1.0, 1.0)
    first = regime_chain(u[:400], *args, 0, 1.0, 1.0)
    second = regime_chain(u[400:], *args, *first[3:])
    for a, b1, b2 in zip(full[:3], first[:3], second[:3], strict=True):
        np.testing.assert_array_equal(a, np.concatenate([b1, b2]))


def test_gjr_garch_has_unit_unconditional_variance_and_clustering():
    alpha, beta, gamma = 0.05, 0.85, 0.08
    omega = 1 - (alpha + beta + gamma / 2)
    z = np.random.default_rng(2).standard_normal((400_000, 1))
    h, *_ = gjr_garch(z, omega, alpha, beta, gamma, np.ones(1), np.zeros(1))
    e = np.sqrt(h[:, 0]) * z[:, 0]
    assert abs(e.var() - 1.0) < 0.05
    a = np.abs(e)
    assert np.corrcoef(a[:-1], a[1:])[0, 1] > 0.05


def test_gjr_garch_is_resumable():
    z = np.random.default_rng(3).standard_normal((500, 3))
    params = (0.1, 0.05, 0.85, 0.0)
    full, *_ = gjr_garch(z, *params, np.ones(3), np.zeros(3))
    h1, v, e = gjr_garch(z[:200], *params, np.ones(3), np.zeros(3))
    h2, *_ = gjr_garch(z[200:], *params, v, e)
    np.testing.assert_array_equal(full, np.vstack([h1, h2]))


def test_ar1_is_resumable_and_persistent():
    u = np.random.default_rng(4).standard_normal((10_000, 2))
    full, _ = ar1(u, 0.7, np.zeros(2))
    y1, s = ar1(u[:3000], 0.7, np.zeros(2))
    y2, _ = ar1(u[3000:], 0.7, s)
    np.testing.assert_array_equal(full, np.vstack([y1, y2]))
    assert abs(np.corrcoef(full[:-1, 0], full[1:, 0])[0, 1] - 0.7) < 0.03


def test_bridge_extremes_bracket_the_body_and_match_brownian_range():
    rng = np.random.default_rng(5)
    n = 200_000
    b = rng.standard_normal(n)  # Brownian increment over a unit bar, std 1
    hi, lo = bridge_extremes(b, np.ones(n), 1 - rng.random(n), 1 - rng.random(n))
    assert np.all(hi >= np.maximum(0, b) - 1e-12)
    assert np.all(lo <= np.minimum(0, b) + 1e-12)
    # E[max - min] of Brownian motion over a unit interval is 2*sqrt(2/pi).
    assert abs((hi - lo).mean() - 2 * np.sqrt(2 / np.pi)) < 0.02


# ---------------------------------------------------------------------------
# Fused kernels must equal, bit for bit, the NumPy expressions they replace
# (ADR 0007: an optimisation never changes a seed's output). The references
# below are the model's NumPy expressions.


def _random_day(seed: int, n: int = 1440, f: int = 7):
    rng = np.random.default_rng(seed)
    return {
        "h": rng.uniform(0.2, 4.0, (n, f)),
        "vol_m": rng.uniform(0.5, 2.0, n),
        "drift_m": rng.uniform(-1.0, 2.0, n),
        "season": rng.uniform(0.3, 2.0, n),
        "z": rng.standard_t(4, (n, f)),
        "sigma": rng.uniform(1e-5, 1e-3, f),
        "mu": rng.normal(0, 1e-7, f),
        "trend": rng.normal(0, 1e-4, f),
        "log_price": np.log(rng.uniform(0.01, 50_000, f)),
    }


def _reference_paths(d, gap_rows, gap_values):
    level = np.sqrt(d["h"]) * d["vol_m"][:, None]
    sigma_f = d["sigma"] * level * d["season"][:, None]
    returns_f = d["mu"] + d["trend"] * d["drift_m"][:, None] + sigma_f * d["z"]
    gap_f = np.zeros_like(returns_f)
    gap_f[gap_rows] = gap_values
    log_close = d["log_price"] + np.cumsum(gap_f + returns_f, axis=0)
    log_open = np.vstack([d["log_price"][None, :], log_close[:-1]]) + gap_f
    return sigma_f, returns_f, log_open, log_close


@pytest.mark.parametrize("gap_rows", [[], [0], [3, 400, 401, 1439]])
def test_factor_paths_equal_the_numpy_expressions_bit_for_bit(gap_rows):
    d = _random_day(11)
    rows = np.asarray(gap_rows, dtype=np.int64)
    gaps = np.random.default_rng(12).normal(0, 1e-3, (rows.size, d["z"].shape[1]))
    got = factor_paths(
        d["h"], d["vol_m"], d["drift_m"], d["season"], d["z"], d["sigma"], d["mu"], d["trend"],
        rows, gaps, d["log_price"],
    )  # fmt: skip
    for a, b in zip(got, _reference_paths(d, rows, gaps), strict=True):
        np.testing.assert_array_equal(a, b)


def test_project_signed_equals_the_matrix_product():
    rng = np.random.default_rng(3)
    x = rng.normal(0, 3, (500, 4))
    # anchors, inverse pairs and two-term crosses, as in the forex structure
    weights = np.array(
        [[1, 0, 0, 0], [0, -1, 0, 0], [1, -1, 0, 0], [0, 1, 0, 1], [-1, 0, 1, 0], [0, 0, 0, 1]],
        dtype=float,
    )
    index = np.full((len(weights), 2), -1, dtype=np.int64)
    sign = np.zeros((len(weights), 2))
    for j, row in enumerate(weights):
        nz = np.nonzero(row)[0]
        index[j, : nz.size], sign[j, : nz.size] = nz, row[nz]
    np.testing.assert_array_equal(project_signed(x, index, sign), x @ weights.T)


def test_bar_kernels_equal_the_numpy_expressions_bit_for_bit():
    rng = np.random.default_rng(5)
    n, m = 1440, 6
    log_open = np.log(rng.uniform(0.5, 300, (n, m)))
    body = rng.normal(0, 1e-3, (n, m))
    log_close = log_open + body
    sigma_i = rng.uniform(1e-5, 2e-3, (n, m))
    sigma_ref = rng.uniform(1e-5, 2e-3, m)
    season = rng.uniform(0.3, 2.0, n)
    u_high, u_low = 1.0 - rng.random((n, m)), 1.0 - rng.random((n, m))
    e_volume = rng.standard_normal((n, m))
    noise = rng.uniform(0.1, 0.5, m)
    correction = rng.uniform(0.0, 0.3, m)
    ratio, share, lam, kappa, phi = 0.62, 0.25, 0.35, 0.8, 0.9
    memory0 = rng.normal(0, 0.5, m)

    # The model's NumPy expressions
    hi, lo = bridge_extremes(body, sigma_i * ratio, u_high, u_low, share)
    open_, close = np.exp(log_open), np.exp(log_close)
    high = np.maximum(np.exp(log_open + hi), np.maximum(open_, close))
    low = np.minimum(np.exp(log_open + lo), np.minimum(open_, close))
    level_i = sigma_i / (sigma_ref * season[:, None])
    zabs = np.clip(np.abs(body) / sigma_i, 0.0, 10.0) - np.sqrt(2.0 / np.pi)
    drivers = lam * zabs + kappa * np.log(level_i) + np.log(season)[:, None] + noise * e_volume
    y, memory_ref = ar1(drivers, phi, memory0)
    volume = np.exp(y - correction)

    prices = np.empty((4, n, m))
    level = np.empty((n, m))
    bar_arguments(
        log_open, log_close, body, sigma_i, ratio, share, np.log(u_high), np.log(u_low),
        sigma_ref, season, prices, level,
    )  # fmt: skip
    np.exp(prices, out=prices)
    np.log(level, out=level)
    memory = memory0.copy()
    got_high, got_low, vol_arg = finish_bars(
        prices, body, sigma_i, level, np.log(season), noise, e_volume,
        lam, kappa, phi, 10.0, float(np.sqrt(2.0 / np.pi)), correction, memory,
    )  # fmt: skip
    np.testing.assert_array_equal(prices[0], open_)
    np.testing.assert_array_equal(prices[1], close)
    np.testing.assert_array_equal(got_high, high)
    np.testing.assert_array_equal(got_low, low)
    np.testing.assert_array_equal(np.exp(vol_arg), volume)
    np.testing.assert_array_equal(memory, memory_ref)


def test_compiled_kernels_equal_their_interpreted_python_bit_for_bit():
    # CPython float arithmetic never fuses a * b + c, so equality with the
    # interpreted kernel proves LLVM did not contract anything into an FMA
    # (which would break bit-exactness). Small inputs: py_func is slow.
    rng = np.random.default_rng(9)
    n, f = 60, 3
    d = _random_day(4, n=n, f=f)
    rows, gaps = np.array([0, 17], dtype=np.int64), rng.normal(0, 1e-3, (2, f))
    paths_args = (
        d["h"], d["vol_m"], d["drift_m"], d["season"], d["z"], d["sigma"], d["mu"], d["trend"],
    )  # fmt: skip
    cases = [
        (factor_paths, (*paths_args, rows, gaps, d["log_price"])),
        (regime_chain, (rng.random(n), _cum([[0.9, 0.1], [0.2, 0.8]]), np.array([1.0, -1.0]),
                        np.array([0.8, 2.0]), 0.1, 0, 1.0, 0.8)),
        (gjr_garch, (rng.standard_normal((n, f)), 0.02, 0.05, 0.9, 0.06, np.ones(f), np.zeros(f))),
        (ar1, (rng.normal(size=(n, f)), 0.95, rng.normal(size=f))),
        (project_signed, (rng.normal(size=(n, f)), np.array([[0, -1], [1, 2]]), np.array([[1.0, 0.0], [-1.0, 1.0]]))),
    ]  # fmt: skip
    for kernel, args in cases:
        compiled, interpreted = kernel(*args), kernel.py_func(*args)
        compiled = compiled if isinstance(compiled, tuple) else (compiled,)
        interpreted = interpreted if isinstance(interpreted, tuple) else (interpreted,)
        for a, b in zip(compiled, interpreted, strict=True):
            np.testing.assert_array_equal(a, b, err_msg=kernel.__name__)

    m = 4
    body = rng.normal(0, 1e-3, (n, m))
    log_open = rng.normal(3, 1, (n, m))
    sigma_i = rng.uniform(1e-5, 2e-3, (n, m))
    season = rng.uniform(0.3, 2.0, n)
    bar_args = (log_open, log_open + body, body, sigma_i, 0.6, 0.25, np.log(rng.random((n, m))),
                np.log(rng.random((n, m))), rng.uniform(1e-5, 2e-3, m), season)  # fmt: skip
    outs = [(np.empty((4, n, m)), np.empty((n, m))) for _ in range(2)]
    bar_arguments(*bar_args, *outs[0])
    bar_arguments.py_func(*bar_args, *outs[1])
    for a, b in zip(outs[0], outs[1], strict=True):
        np.testing.assert_array_equal(a, b)
    prices, level = np.exp(outs[0][0]), np.log(outs[0][1])
    finish_args = (prices, body, sigma_i, level, np.log(season), rng.uniform(0.1, 0.5, m),
                   rng.standard_normal((n, m)), 0.35, 0.8, 0.9, 10.0, 0.79, rng.uniform(0, 0.3, m))  # fmt: skip
    memory0 = rng.normal(size=m)
    memory = [memory0.copy(), memory0.copy()]
    a = finish_bars(*finish_args, memory[0])
    b = finish_bars.py_func(*finish_args, memory[1])
    for x, y in zip((*a, memory[0]), (*b, memory[1]), strict=True):
        np.testing.assert_array_equal(x, y)


def test_without_numba_on_emscripten_the_output_is_unchanged():
    # Pyodide (sys.platform "emscripten") has no Numba: the kernels run as
    # plain Python there and must give the same bits as the compiled ones.
    # Elsewhere a missing Numba must fail loudly, not fall back.
    #
    # The platform is faked only while the kernels module is imported, the
    # one place that reads it. Every other module is first loaded under the
    # real platform, and the fake is undone before generating: stdlib and
    # dependencies branch on sys.platform at import and at call time (on
    # Windows before Python 3.14, threadpoolctl took its Unix libc path and
    # failed), so a process-wide fake tests a platform that does not exist.
    code = """
import hashlib, sys
import numpy as np

def fingerprint():
    import marketforge as mf
    data = mf.generate(["BTCUSD", "AAPL"], start="2024-01-02", days=1, seed=5,
                       timeframes=["m1"], with_regime=True, with_spread=True)
    frame = data.to_long()
    values = frame.select_dtypes("number").to_numpy(dtype="float64")
    return hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest()

if sys.argv[1] == "emscripten":
    import marketforge  # load every dependency under the real platform
    for name in [m for m in sys.modules if m.partition(".")[0] == "marketforge"]:
        del sys.modules[name]
    sys.modules["numba"] = None  # any `import numba` now raises ImportError
    loaded, real_platform = set(sys.modules), sys.platform
    sys.platform = "emscripten"
    try:
        from marketforge.simulation import kernels
    finally:
        sys.platform = real_platform
    leaked = sorted(
        m for m in set(sys.modules) - loaded if m.partition(".")[0] != "marketforge"
    )
    assert not leaked, f"imported under the fake platform: {leaked}"
    assert not hasattr(kernels.regime_chain, "signatures"), "kernels were compiled"
elif sys.argv[1] == "missing":
    sys.modules["numba"] = None
    try:
        import marketforge  # noqa: F401
    except ImportError:
        print("refused")
    sys.exit()
print(fingerprint())
"""

    def run(mode: str) -> str:
        done = subprocess.run([sys.executable, "-c", code, mode], capture_output=True, text=True)
        if done.returncode:
            pytest.fail(f"{mode} run exited with {done.returncode}:\n{done.stderr}")
        return done.stdout.strip()

    assert run("emscripten") == run("native")
    assert run("missing") == "refused"
