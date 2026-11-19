"""Tests for the documentation-examples check (.github/scripts/doc_examples.py)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github" / "scripts" / "doc_examples.py"
if not SCRIPT.is_file():  # running from the sdist, which ships tests/ but not .github/
    pytest.skip("release tooling is not part of the sdist", allow_module_level=True)

_spec = importlib.util.spec_from_file_location("doc_examples", SCRIPT)
assert _spec is not None and _spec.loader is not None
docs = importlib.util.module_from_spec(_spec)
sys.modules["doc_examples"] = docs
_spec.loader.exec_module(docs)

PAGE = Path("page.md")


def _block(code, language="python", mode="run", line=10):
    return docs.Block(PAGE, line, language, mode, code)


# ------------------------------------------------------------- extraction


def test_extracts_checked_languages_with_their_page_line_and_mode():
    text = "\n".join(
        [
            "# Title",  # 1
            "```bash",  # 2
            "marketforge --version",  # 3
            "```",  # 4
            "```csv",  # 5
            "a,b",  # 6
            "```",  # 7
            "1. A list item:",  # 8
            "   ~~~python check=static",  # 9
            "   import marketforge as mf",  # 10
            "       x = 1",  # 11
            "   ~~~",  # 12
        ]
    )
    blocks = docs.extract_blocks(PAGE, text)
    assert [(b.language, b.mode, b.line) for b in blocks] == [
        ("shell", "run", 3),
        ("python", "static", 10),
    ]
    assert blocks[1].code == "import marketforge as mf\n    x = 1"


def test_a_longer_fence_can_contain_a_shorter_one():
    text = "````markdown\n```python\nboom(\n```\n````\n```python\nx = 1\n```\n"
    [block] = docs.extract_blocks(PAGE, text)
    assert block.code == "x = 1" and block.line == 7


def test_an_unknown_check_flag_and_an_unclosed_block_are_errors():
    with pytest.raises(docs.ExampleError, match="unknown check=skip"):
        docs.extract_blocks(PAGE, "```python check=skip\nx\n```\n")
    with pytest.raises(docs.ExampleError, match="never closed"):
        docs.extract_blocks(PAGE, "```python\nx\n")


# ------------------------------------------------------------------ shell


def test_shell_commands_follow_continuations_comments_and_separators():
    block = _block(
        "pip install marketforge\n"
        "# a comment line\n"
        "marketforge generate -o ./data \\\n"
        "    --from 2024-01-01 --days 2   # trailing comment\n"
        "cd x && marketforge validate a.csv; git status\n",
        language="shell",
        line=20,
    )
    commands = docs.shell_commands(block, substitute=False)
    assert [(c.line, c.args) for c in commands] == [
        (22, ["generate", "-o", "./data", "--from", "2024-01-01", "--days", "2"]),
        (24, ["validate", "a.csv"]),
    ]


def test_shell_variables_and_loops_cannot_run_but_can_be_checked():
    loop = _block(
        "for seed in $(seq 0 3); do\n  marketforge generate --from 2024-01-01 --seed $seed\ndone",
        language="shell",
    )
    with pytest.raises(docs.ExampleError, match="check=static"):
        docs.shell_commands(loop, substitute=False)
    [command] = docs.shell_commands(loop, substitute=True)
    assert command.args == ["generate", "--from", "2024-01-01", "--seed", "0"]


# ----------------------------------------------------------------- python


def test_python_calls_must_bind_to_the_real_signature():
    docs.check_python_api(_block('mf.generate("EURUSD", start="a", end="b", seed=1)'))
    with pytest.raises(docs.ExampleError, match="unexpected keyword argument 'assets'") as e:
        docs.check_python_api(_block('x = 1\nmf.generate(assets="EURUSD", start="a", end="b")'))
    assert e.value.line == 11


def test_python_names_must_be_public():
    with pytest.raises(docs.ExampleError, match=r"`mf\.generate_dataset` is not"):
        docs.check_python_api(_block("mf.generate_dataset()"))
    with pytest.raises(docs.ExampleError, match=r"`mf\.engine` is not"):
        docs.check_python_api(_block("print(mf.engine)"))
    with pytest.raises(docs.ExampleError, match="from marketforge import simulate"):
        docs.check_python_api(_block("from marketforge import simulate"))
    # Another alias, and calls that cannot be bound statically, are fine.
    docs.check_python_api(_block("import marketforge as m\nm.generate(*xs, **kw)"))


def test_invalid_python_points_at_the_page_line():
    with pytest.raises(docs.ExampleError, match="invalid Python") as e:
        docs.check_python_api(_block("x = 1\ny = (", line=5))
    assert e.value.line == 6


def test_a_failing_example_reports_the_page_line_of_the_error():
    namespace: dict = {}
    with pytest.raises(docs.ExampleError, match="ZeroDivisionError") as e:
        docs.run_python(_block("a = 1\nb = a / 0\n", line=30), namespace)
    assert e.value.line == 31


def test_a_displayed_signature_must_match_the_real_one():
    real = (
        "mf.extend(\n    dataset, end=None, *, days=None, jobs=None, on_day=None,\n) -> DiskReport"
    )
    docs.check_signature(_block(real, mode="signature"))
    for wrong, reason in [
        (
            "mf.extend(dataset, end=None, *, days=None, jobs=2, on_day=None) -> DiskReport",
            "differs",
        ),
        (
            "mf.extend(dataset, end=None, days=None, jobs=None, on_day=None) -> DiskReport",
            "differs",
        ),
        ("mf.extend(dataset, *, days=None, jobs=None, on_day=None) -> DiskReport", "differs"),
        (
            "mf.extend(dataset, end=None, *, days=None, jobs=None, on_day=None) -> Report",
            "returns DiskReport",
        ),
        ("extend(dataset)", "expects"),
    ]:
        with pytest.raises(docs.ExampleError, match=reason):
            docs.check_signature(_block(wrong, mode="signature"))


# -------------------------------------------------------------------- cli


def test_generate_is_planned_with_dry_run_and_refuses_unknown_names():
    docs.check_command(
        docs.Command(
            1, ["generate", "-o", "d", "--from", "2024-01-01", "--days", "2", "-i", "EURUSD"]
        )
    )
    with pytest.raises(docs.ExampleError, match="NOTASYMBOL"):
        docs.check_command(
            docs.Command(1, ["generate", "--from", "2024-01-01", "--days", "2", "-i", "NOTASYMBOL"])
        )


def test_other_commands_are_parsed_without_needing_their_files():
    docs.check_command(docs.Command(1, ["validate", "missing.csv", "--market", "forex"]))
    docs.check_command(docs.Command(1, ["--version"]))
    with pytest.raises(docs.ExampleError, match="No such option"):
        docs.check_command(docs.Command(1, ["validate", "--file", "x.csv"]))
    with pytest.raises(docs.ExampleError, match="no such command"):
        docs.check_command(docs.Command(1, ["list-assets"]))


# ------------------------------------------------------------------- toml


def test_toml_is_loaded_as_overrides_and_a_named_block_is_written(tmp_path):
    named = _block("# mine.toml\n[instruments.BTCUSD]\nvolatility = 0.9\n", language="toml")
    docs.check_toml(named, tmp_path)
    assert (tmp_path / "mine.toml").is_file()

    anonymous = _block("[instruments.BTCUSD]\nvolatility = 0.9\n", language="toml")
    docs.check_toml(anonymous, tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["mine.toml"]

    with pytest.raises(docs.ExampleError, match="volatilty"):
        docs.check_toml(
            _block("[instruments.BTCUSD]\nvolatilty = 0.9\n", language="toml"), tmp_path
        )


# ------------------------------------------------------------------- page


def test_a_page_runs_its_examples_in_order_in_a_fresh_directory(tmp_path):
    page = tmp_path / "page.md"
    page.write_text(
        "```bash\n"
        "marketforge generate -o ./data --from 2024-01-02 --days 1 -i EURUSD -t H1 --seed 1\n"
        "```\n"
        "```python\n"
        "import pandas as pd\n"
        'frame = pd.read_csv("data/forex/EURUSD_H1.csv")\n'
        "assert len(frame) > 0\n"
        "```\n"
        "```python\n"
        "assert frame is not None  # names carry over between blocks\n"
        "```\n"
        "```bash check=none\n"
        "marketforge frobnicate\n"
        "```\n",
        encoding="utf-8",
    )
    report = docs.Report()
    docs.check_page(page, report)
    assert report.errors == []
    assert report.checked["run"] == 3 and report.checked["none"] == 1
    assert not (tmp_path / "data").exists()


def test_a_broken_example_is_reported_with_its_page_and_line(tmp_path):
    page = tmp_path / "page.md"
    page.write_text(
        "Text\n\n```python\nmf.instruments('forex')\nmf.nope()\n```\n", encoding="utf-8"
    )
    report = docs.Report()
    docs.check_page(page, report)
    [(path, line, message)] = report.errors
    assert path == page and line == 5 and "mf.nope" in message
