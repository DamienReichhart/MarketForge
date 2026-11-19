import datetime as dt
import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest

import marketforge as mf
from marketforge.api import disk, execution
from marketforge.output import manifest as manifest_module
from marketforge.output.manifest import read_manifest

# Short first generations hold no weekly candle yet; that is the point of these tests.
pytestmark = pytest.mark.filterwarnings("ignore:No candles for")

INSTRUMENTS = "EURUSD,EURJPY,XAUUSD,AAPL,BRK.B,BTCUSD,XRPUSD"
START = "2024-01-03T10:00"  # mid-week, mid-session
END = "2024-02-02T15:17"
OPTIONS = {
    "seed": 0,
    "anomalies": "spikes,flash_crash",
    "include_regime": True,
    "include_spread": True,
}


def _files(root: Path) -> dict[str, Path]:
    return {
        p.relative_to(root).as_posix(): p
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name != "marketforge.json"
    }


def _whole(tmp_path_factory, fmt: str) -> Path:
    root = tmp_path_factory.mktemp(f"whole-{fmt}")
    mf.generate_to_disk(root, INSTRUMENTS, start=START, end=END, fmt=fmt, **OPTIONS)
    return root


@pytest.fixture(scope="module")
def whole_csv(tmp_path_factory):
    return _whole(tmp_path_factory, "csv")


@pytest.fixture(scope="module")
def whole_parquet(tmp_path_factory):
    return _whole(tmp_path_factory, "parquet")


# Cuts on a weekend, in a stock session, just after the forex week opens, a
# few minutes after the start, and two that fall in the same UTC day.
CUTS = [
    ("2024-01-03T10:07",),
    ("2024-01-06T12:00",),
    ("2024-01-16T15:03",),
    ("2024-01-21T22:30", "2024-01-29T00:00"),
    ("2024-01-12T03:00", "2024-01-12T21:59", "2024-01-25T14:31"),
]


@pytest.mark.parametrize("cuts", CUTS)
def test_an_extended_csv_dataset_is_byte_identical_to_one_generation(tmp_path, whole_csv, cuts):
    mf.generate_to_disk(tmp_path, INSTRUMENTS, start=START, end=cuts[0], **OPTIONS)
    for end in (*cuts[1:], END):
        report = mf.extend(tmp_path, end)
    expected, got = _files(whole_csv), _files(tmp_path)
    assert list(got) == list(expected) and len(got) == 7 * 8
    for name, path in expected.items():
        assert got[name].read_bytes() == path.read_bytes(), name
    # Same checkpoint too: extending again continues like the single generation.
    assert report.manifest.read_text() == (whole_csv / "marketforge.json").read_text()
    assert report.n_files == 7 * 8 and report.seed == 0


def test_an_extended_parquet_dataset_holds_the_same_candles(tmp_path, whole_parquet):
    mf.generate_to_disk(
        tmp_path, INSTRUMENTS, start=START, end="2024-01-16T15:03", fmt="parquet", **OPTIONS
    )
    mf.extend(tmp_path, "2024-01-16T15:04")  # one more minute: most files get nothing new
    mf.extend(tmp_path, END, jobs=3)
    expected, got = _files(whole_parquet), _files(tmp_path)
    assert list(got) == list(expected)
    for name, path in expected.items():
        assert pq.read_table(got[name]).equals(pq.read_table(path)), name


def test_the_manifest_records_how_the_dataset_was_produced(tmp_path):
    overrides = {"MYCOIN": {"market": "crypto", "start_price": 1.5, "volatility": 0.9}}
    report = mf.generate_to_disk(
        tmp_path,
        "mycoin,EURUSD",
        start="2024-01-01",
        end="2024-01-03",
        seed=7,
        timeframes="h1",
        overrides=overrides,
    )
    doc = json.loads(report.manifest.read_text())
    assert report.manifest == tmp_path / "marketforge.json"
    assert {k: doc[k] for k in list(doc)[:-1]} == {
        "marketforge": mf.__version__,
        "model_revision": mf.MODEL_REVISION,
        "seed": 7,
        "start": "2024-01-01T00:00:00Z",
        "end": "2024-01-03T00:00:00Z",
        "format": "csv",
        "timestamps": "unix",
        "timeframes": ["H1"],
        "anomalies": [],
        "include_regime": False,
        "include_spread": False,
        "include_bid_ask": False,
        "instruments": {"crypto": ["MYCOIN"], "forex": ["EURUSD"]},
        "overrides": overrides,
    }
    # The overrides travel with the dataset: extending needs no file.
    mf.extend(tmp_path, dt.date(2024, 1, 4))
    assert len((tmp_path / "crypto" / "MYCOIN_H1.csv").read_text().splitlines()) == 1 + 72


def test_extend_refuses_what_it_cannot_continue(tmp_path):
    with pytest.raises(ValueError, match="is not a MarketForge dataset"):
        mf.extend(tmp_path, "2024-02-01")
    mf.generate_to_disk(tmp_path, "AAPL", start="2024-01-02", end="2024-01-05", seed=1)
    with pytest.raises(ValueError, match=r"already ends at 2024-01-05T00:00:00Z"):
        mf.extend(tmp_path, "2024-01-05")
    manifest = tmp_path / "marketforge.json"
    doc = json.loads(manifest.read_text())
    manifest.write_text(json.dumps({**doc, "marketforge": "2.0.0", "model_revision": 0}))
    with pytest.raises(ValueError, match=r"written by MarketForge 2\.0\.0 \(model revision 0\)"):
        mf.extend(tmp_path, "2024-02-01")
    manifest.write_text(json.dumps({k: v for k, v in doc.items() if k != "seed"}))
    with pytest.raises(ValueError, match="not a valid manifest"):
        mf.extend(tmp_path, "2024-02-01")


def test_generating_again_replaces_the_dataset_and_its_manifest(tmp_path):
    mf.generate_to_disk(tmp_path, "AAPL", start="2024-01-02", end="2024-01-05", seed=1)
    mf.generate_to_disk(
        tmp_path, "AAPL", start="2024-01-02", end="2024-01-04", seed=2, overwrite=True
    )
    manifest = read_manifest(tmp_path)
    assert (manifest.seed, manifest.end) == (2, 1704326400)


@pytest.mark.parametrize("fmt", ["csv", "parquet"])
def test_a_failed_extension_leaves_the_dataset_as_it_was(tmp_path, monkeypatch, fmt):
    mf.generate_to_disk(
        tmp_path, "BTCUSD,ETHUSD", start="2024-01-01", end="2024-01-10", seed=3, fmt=fmt
    )
    before = {name: path.read_bytes() for name, path in _files(tmp_path).items()}
    manifest = (tmp_path / "marketforge.json").read_text()

    real = execution.MarketSimulator.simulate_day
    calls = []

    def fails_late(self, day, start, end):
        calls.append(day)
        if len(calls) > 40:
            raise RuntimeError("disk on fire")
        return real(self, day, start, end)

    monkeypatch.setattr(execution.MarketSimulator, "simulate_day", fails_late)
    with pytest.raises(RuntimeError, match="disk on fire"):
        mf.extend(tmp_path, "2024-03-01")
    monkeypatch.undo()
    assert {name: path.read_bytes() for name, path in _files(tmp_path).items()} == before
    assert (tmp_path / "marketforge.json").read_text() == manifest
    mf.extend(tmp_path, "2024-01-12")  # and it can still be extended
    assert read_manifest(tmp_path).end == 1705017600


@pytest.mark.parametrize("fmt", ["csv", "parquet"])
@pytest.mark.parametrize("killed", ["while generating", "while swapping files in"])
def test_an_extension_killed_midway_is_undone_or_finished_by_the_next_one(
    tmp_path, monkeypatch, fmt, killed
):
    kwargs = {"start": "2024-01-01", "seed": 3, "fmt": fmt, "timeframes": "m1,H4,W1"}
    mf.generate_to_disk(tmp_path / "killed", "BTCUSD,ETHUSD", end="2024-01-10", **kwargs)
    mf.generate_to_disk(tmp_path / "whole", "BTCUSD,ETHUSD", end="2024-01-25", **kwargs)

    def dies(*_):
        raise KeyboardInterrupt

    if killed == "while generating":  # nothing gets the chance to clean up
        monkeypatch.setattr(disk, "recover", lambda root: None)
        monkeypatch.setattr(disk, "commit_extension", dies)
    else:  # the new manifest is ready but the files are not swapped in yet
        monkeypatch.setattr(manifest_module, "recover", dies)
    with pytest.raises(KeyboardInterrupt):
        mf.extend(tmp_path / "killed", "2024-01-20")
    monkeypatch.undo()

    mf.extend(tmp_path / "killed", "2024-01-25")
    expected, got = _files(tmp_path / "whole"), _files(tmp_path / "killed")
    assert list(got) == list(expected)
    for name, path in expected.items():
        if fmt == "csv":
            assert got[name].read_bytes() == path.read_bytes(), name
        else:
            assert pq.read_table(got[name]).equals(pq.read_table(path)), name


def test_iso_timestamps_survive_an_extension_and_validation(tmp_path):
    kwargs = {"start": "2024-01-02", "seed": 4, "timeframes": "m1,H1", "timestamps": "iso"}
    mf.generate_to_disk(tmp_path / "whole", "BTCUSD", end="2024-01-20", **kwargs)
    report = mf.generate_to_disk(tmp_path / "part", "BTCUSD", end="2024-01-09T07:21", **kwargs)
    mf.extend(tmp_path / "part", "2024-01-20")
    h1, m1 = (report.paths["crypto"]["BTCUSD"][tf] for tf in ("H1", "m1"))
    assert h1.read_text().splitlines()[:2][1].startswith("2024-01-02T00:00:00Z,")
    assert h1.read_text().splitlines()[-1].startswith("2024-01-19T23:00:00Z,")
    assert m1.read_bytes() == (tmp_path / "whole" / "crypto" / "BTCUSD_m1.csv").read_bytes()
    assert mf.validate(m1).passed
    with pytest.raises(ValueError, match="ISO timestamps are for CSV files"):
        mf.generate_to_disk(tmp_path / "pq", "BTCUSD", end="2024-01-03", fmt="parquet", **kwargs)


def test_extend_continues_a_dataset_from_another_version_with_the_same_model_revision(tmp_path):
    # A patch release that does not touch the model must not strand datasets.
    mf.generate_to_disk(tmp_path, "AAPL", start="2024-01-02", end="2024-01-05", seed=1)
    manifest = tmp_path / "marketforge.json"
    doc = json.loads(manifest.read_text())
    manifest.write_text(json.dumps({**doc, "marketforge": "4.0.1"}))
    mf.extend(tmp_path, "2024-01-09")
    assert read_manifest(tmp_path).end == mf.parse_time("2024-01-09")


@pytest.mark.parametrize("killed", ["while generating", "while swapping files in"])
def test_recovering_an_extension_leaves_files_marketforge_did_not_write_alone(
    tmp_path, monkeypatch, killed
):
    mf.generate_to_disk(
        tmp_path, "BTCUSD", start="2024-01-01", end="2024-01-05", seed=3, fmt="parquet"
    )
    (tmp_path / "notebooks").mkdir()
    theirs = tmp_path / "notebooks" / "work.tmp"
    theirs.write_text("mine")
    beside = tmp_path / "crypto" / "notes.tmp"
    beside.write_text("also mine")

    def dies(*_):
        raise KeyboardInterrupt

    if killed == "while generating":
        monkeypatch.setattr(disk, "recover", lambda root: None)
        monkeypatch.setattr(disk, "commit_extension", dies)
    else:
        monkeypatch.setattr(manifest_module, "recover", dies)
    with pytest.raises(KeyboardInterrupt):
        mf.extend(tmp_path, "2024-01-08")
    monkeypatch.undo()
    manifest_module.recover(tmp_path)
    assert theirs.read_text() == "mine"
    assert beside.read_text() == "also mine"
    assert not (tmp_path / "notebooks" / "work").exists()
