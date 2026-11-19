import json

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.feather as feather
import pyarrow.parquet as pq
import pytest
from click.testing import CliRunner

import marketforge as mf
from marketforge.cli.main import cli

KWARGS = {
    "start": "2024-01-02",
    "days": 6,
    "seed": 5,
    "timeframes": "m1,H1,D1",
    "with_regime": True,
    "with_spread": True,
}
INSTRUMENTS = "BTCUSD,ETHUSD,EURUSD,AAPL"


@pytest.mark.parametrize("fmt", ["parquet", "feather"])
def test_the_long_layout_holds_the_split_layouts_candles(tmp_path, fmt):
    split = mf.generate_to_disk(tmp_path / "split", INSTRUMENTS, format=fmt, **KWARGS)
    long = mf.generate_to_disk(tmp_path / "long", INSTRUMENTS, format=fmt, layout="long", **KWARGS)
    assert long.n_files == 9 and split.n_files == 12 * 1  # 3 markets x 3 timeframes; 4 x 3
    path = tmp_path / "long" / "crypto" / f"m1.{fmt}"
    table = pq.read_table(path) if fmt == "parquet" else feather.read_table(path)
    assert table.column_names[:3] == ["timestamp", "symbol", "market"]
    frame = table.to_pandas()
    assert frame["symbol"].astype(str).tolist()[:4] == ["BTCUSD", "ETHUSD", "BTCUSD", "ETHUSD"]
    assert frame["timestamp"].is_monotonic_increasing
    a, b = mf.read(tmp_path / "split"), mf.read(tmp_path / "long")
    for symbol in a:
        for tf in a[symbol]:
            pd.testing.assert_frame_equal(a[symbol][tf], b[symbol][tf])


def test_the_long_layout_extends_and_verifies(tmp_path):
    whole = mf.generate_to_disk(
        tmp_path / "whole", INSTRUMENTS, format="parquet", layout="long", **KWARGS
    )
    kwargs = {**KWARGS, "days": 3}
    mf.generate_to_disk(tmp_path / "part", INSTRUMENTS, format="parquet", layout="long", **kwargs)
    mf.extend(tmp_path / "part", days=3)
    for path in whole.files:
        rel = path.relative_to(tmp_path / "whole")
        assert pq.read_table(tmp_path / "part" / rel).equals(pq.read_table(path)), rel
    assert mf.verify(tmp_path / "part").passed
    assert mf.info(tmp_path / "part").layout == "long"


def test_the_long_layout_is_not_for_csv(tmp_path):
    with pytest.raises(ValueError, match="long layout is for Parquet and Feather"):
        mf.generate_to_disk(tmp_path, "BTCUSD", layout="long", **KWARGS)
    res = CliRunner().invoke(
        cli,
        [
            "generate",
            "-o",
            str(tmp_path),
            "--from",
            "2024-01-02",
            "--days",
            "1",
            "--layout",
            "long",
        ],
    )
    assert res.exit_code == 2 and "--format parquet" in res.output


def test_files_say_what_they_hold(tmp_path):
    mf.generate_to_disk(tmp_path, "BTCUSD", format="parquet", **KWARGS)
    meta = pq.read_schema(tmp_path / "crypto" / "BTCUSD_H1.parquet").metadata
    doc = {k.decode(): v.decode() for k, v in meta.items()}
    assert doc == {
        "marketforge": mf.__version__,
        "model_revision": str(mf.MODEL_REVISION),
        "seed": "5",
        "market": "crypto",
        "timeframe": "H1",
        "symbol": "BTCUSD",
    }


def test_feather_files_are_uncompressed_so_reads_are_zero_copy(tmp_path):
    mf.generate_to_disk(tmp_path, "BTCUSD", format="feather", **KWARGS)
    path = tmp_path / "crypto" / "BTCUSD_m1.feather"
    pool = pa.default_memory_pool()
    before = pool.bytes_allocated()
    with pa.memory_map(str(path)) as source:
        table = pa.ipc.open_file(source).read_all()
        assert table.num_rows == 8640
        assert pool.bytes_allocated() - before < 64 * 1024  # nothing decompressed
        assert np.isfinite(table["close"].to_numpy()).all()


def test_verify_checksums_without_regenerating(tmp_path):
    mf.generate_to_disk(tmp_path, "BTCUSD", **KWARGS)
    assert mf.verify(tmp_path, checksums=True).passed
    path = tmp_path / "crypto" / "BTCUSD_H1.csv"
    path.write_text(path.read_text().replace(",", ";", 1))
    report = mf.verify(tmp_path, checksums=True)
    assert report.differs == ["crypto/BTCUSD_H1.csv"] and not report.passed
    res = CliRunner().invoke(cli, ["verify", str(tmp_path), "--checksums"])
    assert res.exit_code == 1 and "2/3 files identical to their recorded checksums" in res.output


def test_verify_checksums_refuses_a_manifest_without_them(tmp_path):
    mf.generate_to_disk(tmp_path, "BTCUSD", **KWARGS)
    manifest = tmp_path / "marketforge.json"
    doc = json.loads(manifest.read_text())
    del doc["files"]
    manifest.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="records no checksums"):
        mf.verify(tmp_path, checksums=True)
