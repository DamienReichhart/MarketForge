import numpy as np
import pandas as pd
from click.testing import CliRunner

from marketforge.cli.parser import validate_command


def test_validate_command_on_a_csv(tmp_path):
    rng = np.random.default_rng(0)
    n = 50_000
    r = rng.standard_t(3.5, size=n) * 0.001
    close = 100.0 * np.exp(np.cumsum(r))
    openp = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(openp, close) * 1.0008
    low = np.minimum(openp, close) * 0.9992
    df = pd.DataFrame({
        "timestamp": np.arange(n) * 60, "open": openp, "high": high,
        "low": low, "close": close, "volume": np.full(n, 1000.0),
    })
    p = tmp_path / "BTCUSD_m1.csv"
    df.to_csv(p, index=False)

    res = CliRunner().invoke(validate_command, ["--input", str(p), "--market", "crypto"])
    assert res.exit_code in (0, 1)
    assert "Validation report" in res.output
