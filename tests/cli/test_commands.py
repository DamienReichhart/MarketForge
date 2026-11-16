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
