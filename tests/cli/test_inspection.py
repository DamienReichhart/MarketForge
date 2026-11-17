import json

from click.testing import CliRunner

import marketforge as mf
from marketforge.cli.main import cli


def _run(*args: str):
    return CliRunner().invoke(cli, list(args))


def _dataset(path, **kwargs):
    options = {"start": "2024-01-02", "end": "2024-01-16", "seed": 7, "timeframes": "m1,H1"}
    mf.generate_to_disk(path, "EURUSD,BTCUSD", **{**options, **kwargs})
    return path


def test_info_summarises_a_dataset(tmp_path):
    _dataset(tmp_path)
    res = _run("info", str(tmp_path))
    assert res.exit_code == 0, res.output
    for text in (
        "Seed        7",
        "2024-01-02 00:00 UTC -> 2024-01-16 00:00 UTC",
        "crypto",
        "BTCUSD",
        "4 csv files",
        "Can extend  yes",
    ):
        assert text in res.output, text


def test_info_as_json(tmp_path):
    _dataset(tmp_path)
    doc = json.loads(_run("info", str(tmp_path), "--json").output)
    assert doc["seed"] == 7
    assert doc["model_revision"] == mf.MODEL_REVISION and doc["extendable"] is True
    assert doc["instruments"] == {"forex": ["EURUSD"], "crypto": ["BTCUSD"]}
    assert doc["files"] == 4 and doc["bytes"] > 0


def test_info_says_why_a_dataset_cannot_be_extended(tmp_path):
    _dataset(tmp_path)
    manifest = tmp_path / "marketforge.json"
    doc = json.loads(manifest.read_text())
    manifest.write_text(json.dumps({**doc, "model_revision": 0}))
    res = _run("info", str(tmp_path))
    assert "Can extend  no: written by model revision 0" in res.output


def test_list_instruments_as_json():
    rows = json.loads(_run("list-instruments", "-m", "forex", "--json").output)
    eurjpy = next(r for r in rows if r["symbol"] == "EURJPY")
    assert eurjpy["market"] == "forex" and eurjpy["derived"] is True and eurjpy["volatility"] > 0


def test_validate_a_whole_dataset(tmp_path):
    _dataset(tmp_path)
    res = _run("validate", "--input", str(tmp_path))
    assert res.exit_code == 0, res.output
    assert "2/2 files pass" in res.output
    doc = json.loads(_run("validate", "--input", str(tmp_path), "--json").output)
    assert sorted(doc) == ["crypto/BTCUSD_m1.csv", "forex/EURUSD_m1.csv"]
    assert doc["forex/EURUSD_m1.csv"]["passed"] is True
    assert "kurtosis" in " ".join(doc["forex/EURUSD_m1.csv"]["metrics"])


def test_validating_a_dataset_without_m1_says_so(tmp_path):
    _dataset(tmp_path, timeframes="H1")
    res = _run("validate", "--input", str(tmp_path))
    assert res.exit_code == 2
    assert "has no m1 files" in res.output and "-t m1" in res.output
