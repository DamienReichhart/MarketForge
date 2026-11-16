import pandas as pd
from click.testing import CliRunner

from marketforge.cli import cli


def _run(*args: str):
    return CliRunner().invoke(cli, list(args))


def test_help_lists_subcommands():
    res = _run("--help")
    assert res.exit_code == 0
    for cmd in ("generate", "validate", "list-assets"):
        assert cmd in res.output


def test_generate_writes_files_and_reports_seed(tmp_path):
    res = _run("generate", "-o", str(tmp_path), "--from", "2024-01-02", "--to", "2024-01-04",
               "--assets", "aapl,EURUSD", "-t", "m1,D1", "--seed", "3", "--no-progress")
    assert res.exit_code == 0, res.output
    assert "Reproduce with --seed 3" in res.output
    df = pd.read_csv(tmp_path / "stocks" / "AAPL_D1.csv")
    assert len(df) == 2
    assert (tmp_path / "forex" / "EURUSD_m1.csv").exists()


def test_legacy_flag_only_invocation_still_works(tmp_path):
    res = _run("-o", str(tmp_path), "--from", "1704153600", "--to", "1704240000",
               "--assets", "BTCUSD", "-t", "m1", "--batch-size", "10", "--no-progress")
    assert res.exit_code == 0, res.output
    assert "deprecated" in res.output
    assert (tmp_path / "crypto" / "BTCUSD_m1.csv").exists()


def test_dry_run_writes_nothing(tmp_path):
    res = _run("generate", "-o", str(tmp_path / "out"), "--from", "2024-01-01", "--to", "2025-01-01",
               "--market", "stocks", "--dry-run")
    assert res.exit_code == 0, res.output
    assert "74 instrument(s)" in res.output and "97,740 open minutes" in res.output
    assert not (tmp_path / "out").exists()


def test_errors_are_one_line_unless_debug(tmp_path):
    res = _run("generate", "-o", str(tmp_path), "--from", "2024-01-01", "--to", "2024-01-02", "--assets", "NOPE")
    assert res.exit_code == 1
    assert "Error: Unknown instrument(s): NOPE" in res.output
    debug = _run("--debug", "generate", "-o", str(tmp_path), "--from", "2024-01-01", "--to", "2024-01-02",
                 "--assets", "NOPE")
    assert isinstance(debug.exception, ValueError)


def test_list_assets_marks_forex_crosses():
    res = _run("list-assets", "--market", "forex")
    assert res.exit_code == 0
    line = next(l for l in res.output.splitlines() if l.strip().startswith("EURJPY"))
    assert "cross" in line


def test_validate_generated_parquet(tmp_path):
    gen = _run("generate", "-o", str(tmp_path), "--from", "2024-01-01", "--to", "2024-01-15",
               "--assets", "BTCUSD", "-t", "m1", "--format", "parquet", "--seed", "1", "--no-progress")
    assert gen.exit_code == 0, gen.output
    res = _run("validate", "--input", str(tmp_path / "crypto" / "BTCUSD_m1.parquet"), "--market", "crypto")
    assert "Validation report (crypto)" in res.output
    assert res.exit_code == 0, res.output
