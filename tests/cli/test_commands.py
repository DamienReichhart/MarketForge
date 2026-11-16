import pandas as pd
from click.testing import CliRunner

from marketforge.cli.main import cli


def _run(*args: str):
    return CliRunner().invoke(cli, list(args))


def test_help_lists_subcommands():
    res = _run("--help")
    assert res.exit_code == 0
    for cmd in ("generate", "validate", "list-instruments"):
        assert cmd in res.output


def test_generate_writes_files_and_reports_seed(tmp_path):
    res = _run(
        "generate",
        "-o",
        str(tmp_path),
        "--from",
        "2024-01-02",
        "--to",
        "2024-01-04",
        "--instruments",
        "aapl,EURUSD",
        "-t",
        "m1,D1",
        "--seed",
        "3",
        "--no-progress",
    )
    assert res.exit_code == 0, res.output
    assert "Reproduce with --seed 3" in res.output
    df = pd.read_csv(tmp_path / "stocks" / "AAPL_D1.csv")
    assert len(df) == 2
    assert (tmp_path / "forex" / "EURUSD_m1.csv").exists()


def test_dry_run_writes_nothing(tmp_path):
    res = _run(
        "generate",
        "-o",
        str(tmp_path / "out"),
        "--from",
        "2024-01-01",
        "--to",
        "2025-01-01",
        "--market",
        "stocks",
        "--dry-run",
    )
    assert res.exit_code == 0, res.output
    assert "74 instrument(s)" in res.output and "97,740 open minutes" in res.output
    assert not (tmp_path / "out").exists()


def test_errors_are_one_line_unless_debug(tmp_path):
    res = _run(
        "generate",
        "-o",
        str(tmp_path),
        "--from",
        "2024-01-01",
        "--to",
        "2024-01-02",
        "--instruments",
        "NOPE",
    )
    assert res.exit_code == 1
    assert "Error: Unknown instrument(s): NOPE" in res.output
    debug = _run(
        "--debug",
        "generate",
        "-o",
        str(tmp_path),
        "--from",
        "2024-01-01",
        "--to",
        "2024-01-02",
        "--instruments",
        "NOPE",
    )
    assert isinstance(debug.exception, ValueError)


def test_list_instruments_marks_forex_crosses():
    res = _run("list-instruments", "--market", "forex")
    assert res.exit_code == 0
    line = next(l for l in res.output.splitlines() if l.strip().startswith("EURJPY"))
    assert "cross" in line


def test_validate_generated_parquet(tmp_path):
    gen = _run(
        "generate",
        "-o",
        str(tmp_path),
        "--from",
        "2024-01-01",
        "--to",
        "2024-01-15",
        "--instruments",
        "BTCUSD",
        "-t",
        "m1",
        "--format",
        "parquet",
        "--seed",
        "1",
        "--no-progress",
    )
    assert gen.exit_code == 0, gen.output
    res = _run("validate", "--input", str(tmp_path / "crypto" / "BTCUSD_m1.parquet"))
    assert "Validation report (crypto)" in res.output
    assert res.exit_code == 0, res.output


def test_generate_takes_lowercase_timeframes_and_warns_about_empty_files(tmp_path):
    res = _run(
        "generate",
        "-o",
        str(tmp_path),
        "--from",
        "2024-01-01",
        "--to",
        "2024-01-01T12:00",
        "--instruments",
        "AAPL",
        "-t",
        "d1",
        "--seed",
        "1",
        "--no-progress",
    )
    assert res.exit_code == 0, res.output
    assert "Warning: No candles for AAPL D1" in res.output


def test_generate_asks_for_an_output_directory_before_planning():
    res = _run("generate", "--from", "2024-01-01", "--to", "2024-01-02", "--instruments", "AAPL")
    assert res.exit_code == 2
    assert "Missing option '--output-dir'" in res.output and "Range" not in res.output


def test_extend_continues_a_dataset_like_one_longer_generation(tmp_path):
    common = ("--instruments", "EURUSD,AAPL", "-t", "m1,D1", "--seed", "3", "--no-progress")
    whole = _run(
        "generate", "-o", str(tmp_path / "whole"), "--from", "2024-01-02", "--days", "9", *common
    )
    assert whole.exit_code == 0, whole.output
    part = _run(
        "generate",
        "-o",
        str(tmp_path / "part"),
        "--from",
        "2024-01-02",
        "--to",
        "2024-01-04T15:00",
        *common,
    )
    assert part.exit_code == 0, part.output

    dry = _run("extend", str(tmp_path / "part"), "--to", "2024-01-11", "--dry-run")
    assert dry.exit_code == 0, dry.output
    assert "2024-01-04 15:00 UTC -> 2024-01-11 00:00 UTC" in dry.output
    assert "added to" in dry.output

    res = _run("extend", str(tmp_path / "part"), "--to", "2024-01-11", "--no-progress")
    assert res.exit_code == 0, res.output
    for name in (
        "forex/EURUSD_m1.csv",
        "forex/EURUSD_D1.csv",
        "stocks/AAPL_m1.csv",
        "stocks/AAPL_D1.csv",
    ):
        assert (tmp_path / "part" / name).read_bytes() == (tmp_path / "whole" / name).read_bytes()

    more = _run("extend", str(tmp_path / "part"), "--days", "1", "--no-progress")
    assert more.exit_code == 0, more.output
    assert "2024-01-11 00:00 UTC -> 2024-01-12 00:00 UTC" in more.output


def test_the_end_of_a_range_is_given_exactly_once(tmp_path):
    for extra in ((), ("--to", "2024-01-03", "--days", "2")):
        res = _run(
            "generate", "-o", str(tmp_path), "--from", "2024-01-02", "--instruments", "AAPL", *extra
        )
        assert res.exit_code == 2 and "exactly one of '--to' and '--days'" in res.output
    res = _run("extend", str(tmp_path), "--days", "2")
    assert res.exit_code == 1 and "is not a MarketForge dataset" in res.output


def test_with_spread_adds_a_spread_column(tmp_path):
    res = _run(
        "generate", "-o", str(tmp_path), "--from", "2024-01-02", "--days", "1",
        "--instruments", "BTCUSD", "-t", "H1", "--with-spread", "--seed", "1", "--no-progress",
    )  # fmt: skip
    assert res.exit_code == 0, res.output
    df = pd.read_csv(tmp_path / "crypto" / "BTCUSD_H1.csv")
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume", "spread"]
    assert (df["spread"] > 0).all()
