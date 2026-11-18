"""Check that the code examples in the documentation still work.

Examples rot silently: a renamed parameter or option breaks every copy-paste
of the README while all tests stay green. This script reads the fenced code
blocks of README.md and of the website's pages and checks each one against
the installed `marketforge`:

python   Every call `mf.NAME(...)` must name a public function and bind to
         its real signature (a renamed or removed parameter fails). Then the
         block runs. Blocks of one page run in order in one namespace, where
         `import marketforge as mf` is already done.
bash     Only `marketforge ...` commands are considered (pip, git, npm, ...
         are not run). A `generate` is planned with `--dry-run`, which checks
         instruments, dates, timeframes and override files without simulating
         anything; the other commands are parsed by the real command-line
         parser. Then the commands run.
toml     Parsed and loaded as an instrument override file. A block whose
         first line is `# NAME.toml` is also written as NAME.toml for the
         page's other examples to use.

Each page runs in its own empty directory, so its examples can write ./data
and read it back. A flag after the language changes what is done to a block:

    ```python check=static     checks only, without running (too long to run
                               in CI, or it uses placeholders the reader fills)
    ```python check=signature  the block shows a signature, `mf.NAME(...) -> T`;
                               it must match the real one exactly
    ```bash check=none         not checked at all

Usage (run with `python -I`, so the installed package is imported, not the
checkout):

    python -I .github/scripts/doc_examples.py [FILE ...]

Without FILEs, every documentation page tracked by git is checked.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import enum
import inspect
import io
import os
import re
import shlex
import subprocess
import sys
import tempfile
import textwrap
import time
import tomllib
import traceback
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DOC_GLOBS = ["README.md", "website/src/content/docs/**/*.md", "website/src/content/docs/**/*.mdx"]

LANGUAGES = {
    "python": "python",
    "py": "python",
    "bash": "shell",
    "sh": "shell",
    "shell": "shell",
    "console": "shell",
    "toml": "toml",
}
MODES = ("run", "static", "signature", "none")
FENCE = re.compile(r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
TOML_NAME = re.compile(r"^#\s*(?P<name>[\w.-]+\.toml)\s*$")
SHELL_CONTROL = re.compile(r"^\s*(for|while|until|if|case|function)\b|\$\(|`")
SHELL_SEPARATORS = {"&&", ";", "||"}


class ExampleError(Exception):
    """A documentation example that does not work. `line` is a line of the page."""

    def __init__(self, line: int, message: str) -> None:
        super().__init__(message)
        self.line = line


@dataclass
class Block:
    path: Path
    line: int  # line of the page holding the block's first line of code
    language: str  # python, shell or toml
    mode: str
    code: str


@dataclass
class Command:
    line: int
    args: list[str]  # without the leading "marketforge"


@dataclass
class Report:
    checked: dict[str, int] = field(default_factory=lambda: dict.fromkeys(MODES, 0))
    errors: list[tuple[Path, int, str]] = field(default_factory=list)


# --------------------------------------------------------------- extraction


def parse_info(info: str, path: Path, line: int) -> tuple[str, str]:
    """(language, mode) of a fence's info string, e.g. 'python check=static'."""
    words = info.split()
    language = words[0].lower() if words else ""
    mode = "run"
    for word in words[1:]:
        if word.startswith("check="):
            mode = word.removeprefix("check=")
            if mode not in MODES:
                raise ExampleError(line, f"unknown check={mode}; use one of {', '.join(MODES)}")
    return language, mode


def extract_blocks(path: Path, text: str) -> list[Block]:
    """The blocks of the languages this script checks, in page order."""
    lines = text.splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        opening = FENCE.match(lines[i])
        if not opening:
            i += 1
            continue
        fence, indent = opening["fence"], opening["indent"]
        end = i + 1
        while end < len(lines) and not (
            lines[end].strip().startswith(fence[0] * len(fence))
            and not lines[end].strip().lstrip(fence[0])
        ):
            end += 1
        if end == len(lines):
            raise ExampleError(i + 1, "code block is never closed")
        language, mode = parse_info(opening["info"], path, i + 1)
        if language in LANGUAGES:
            body = [line.removeprefix(indent) for line in lines[i + 1 : end]]
            blocks.append(
                Block(path, i + 2, LANGUAGES[language], mode, textwrap.dedent("\n".join(body)))
            )
        i = end + 1
    return blocks


def shell_commands(block: Block, *, substitute: bool) -> list[Command]:
    """
    The `marketforge` commands of a shell block, one per logical line and
    separator. With `substitute`, shell variables become "0", so a command in
    a loop can still be parsed; without it, they are an error.
    """
    logical: list[tuple[int, str]] = []
    pending: list[str] = []
    first = 0
    for offset, raw in enumerate(block.code.splitlines()):
        if not pending:
            first = block.line + offset
        if raw.rstrip().endswith("\\"):
            pending.append(raw.rstrip()[:-1])
            continue
        pending.append(raw)
        logical.append((first, " ".join(pending)))
        pending = []
    if pending:
        logical.append((first, " ".join(pending)))

    commands = []
    for line, text in logical:
        if SHELL_CONTROL.search(text) and not substitute:
            raise ExampleError(
                line,
                "shell control flow or substitution cannot be run: mark the block check=static",
            )
        try:
            # punctuation_chars: `a.csv;` is two tokens, as in a shell.
            lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
            lexer.whitespace_split = True
            tokens = list(lexer)
        except ValueError as e:
            raise ExampleError(line, f"cannot parse the shell line: {e}") from e
        group: list[str] = []
        for token in [*tokens, ";"]:
            if token not in SHELL_SEPARATORS:
                group.append(token)
                continue
            if group and group[0] == "marketforge":
                args = group[1:]
                if any("$" in arg for arg in args):
                    if not substitute:
                        raise ExampleError(
                            line,
                            "uses shell variables and cannot be run: mark the block check=static",
                        )
                    args = [re.sub(r"\$\{?\w+\}?", "0", arg) for arg in args]
                commands.append(Command(line, args))
            group = []
    return commands


# ------------------------------------------------------------------ checks


def _public_api() -> Any:
    import marketforge

    return marketforge


def _call_name(node: ast.AST, aliases: set[str]) -> str | None:
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in aliases
    ):
        return node.attr
    return None


def check_python_api(block: Block) -> ast.Module:
    """Fail on a call or attribute of `mf` that the installed package does not have."""
    mf = _public_api()
    try:
        tree = ast.parse(block.code)
    except SyntaxError as e:
        raise ExampleError(block.line + (e.lineno or 1) - 1, f"invalid Python: {e.msg}") from e

    aliases = {"mf"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            aliases |= {a.asname or a.name for a in node.names if a.name == "marketforge"}
        elif isinstance(node, ast.ImportFrom) and node.module == "marketforge":
            for alias in node.names:
                if alias.name not in mf.__all__:
                    raise ExampleError(
                        block.line + node.lineno - 1,
                        f"`from marketforge import {alias.name}`: not in marketforge's public API",
                    )

    for node in ast.walk(tree):
        line = block.line + getattr(node, "lineno", 1) - 1
        if isinstance(node, ast.Call) and (name := _call_name(node.func, aliases)):
            if name not in mf.__all__:
                raise ExampleError(line, f"`mf.{name}` is not in marketforge's public API")
            if any(isinstance(a, ast.Starred) for a in node.args) or any(
                k.arg is None for k in node.keywords
            ):
                continue
            try:
                inspect.signature(getattr(mf, name)).bind(
                    *[None] * len(node.args), **{k.arg: None for k in node.keywords if k.arg}
                )
            except TypeError as e:
                raise ExampleError(line, f"`mf.{name}(...)`: {e}") from e
        elif (name := _call_name(node, aliases)) and name not in mf.__all__:
            raise ExampleError(line, f"`mf.{name}` is not in marketforge's public API")
    return tree


SIGNATURE = re.compile(r"^\s*mf\.(?P<name>\w+)\((?P<params>.*)\)\s*->\s*(?P<returns>.+?)\s*$", re.S)


def check_signature(block: Block) -> None:
    """A displayed signature `mf.NAME(params) -> T` must match the real one."""
    match = SIGNATURE.match(block.code)
    if not match:
        raise ExampleError(block.line, "check=signature expects `mf.NAME(parameters) -> TYPE`")
    mf = _public_api()
    name = match["name"]
    if name not in mf.__all__:
        raise ExampleError(block.line, f"`mf.{name}` is not in marketforge's public API")
    try:
        shown = ast.parse(f"def {name}({match['params']}) -> {match['returns']}: ...").body[0]
    except SyntaxError as e:
        raise ExampleError(block.line, f"cannot read the signature: {e.msg}") from e
    assert isinstance(shown, ast.FunctionDef)

    def described(arguments: ast.arguments) -> list[str]:
        positional = [*arguments.posonlyargs, *arguments.args]
        defaults = [None] * (len(positional) - len(arguments.defaults)) + list(arguments.defaults)
        out = [_param(a.arg, d) for a, d in zip(positional, defaults, strict=True)]
        if arguments.vararg:
            out.append("*" + arguments.vararg.arg)
        elif arguments.kwonlyargs:
            out.append("*")
        out += [
            _param(a.arg, d)
            for a, d in zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True)
        ]
        if arguments.kwarg:
            out.append("**" + arguments.kwarg.arg)
        return out

    real = inspect.signature(getattr(mf, name))
    real_params = str(real).rsplit(" -> ", 1)[0]
    expected = ast.parse(f"def f{_strip_annotations(real)}: ...").body[0]
    assert isinstance(expected, ast.FunctionDef)
    if described(shown.args) != described(expected.args):
        raise ExampleError(
            block.line,
            f"the signature shown for mf.{name} differs from the real one: "
            f"({', '.join(described(shown.args))}) vs {real_params}",
        )
    shown_return = ast.unparse(shown.returns) if shown.returns else ""
    real_return = real.return_annotation
    real_return = (
        real_return if isinstance(real_return, str) else getattr(real_return, "__name__", "")
    )
    if real_return and shown_return != real_return:
        raise ExampleError(
            block.line, f"mf.{name} returns {real_return}, the page says {shown_return}"
        )


def _param(name: str, default: ast.expr | None) -> str:
    return name if default is None else f"{name}={ast.unparse(default)}"


def _strip_annotations(signature: inspect.Signature) -> str:
    # An enum default is shown as its value (`fmt="csv"`), which is what a
    # reader passes; its repr (`<OutputFormat.CSV: 'csv'>`) is not Python.
    plain = signature.replace(
        parameters=[
            p.replace(
                annotation=inspect.Parameter.empty,
                default=p.default.value if isinstance(p.default, enum.Enum) else p.default,
            )
            for p in signature.parameters.values()
        ],
        return_annotation=inspect.Signature.empty,
    )
    return str(plain)


@contextlib.contextmanager
def _paths_need_not_exist(command: Any) -> Iterator[None]:
    """Parse a command without requiring the files it names to exist yet."""
    import click

    relaxed = [p.type for p in command.params if isinstance(p.type, click.Path) and p.type.exists]
    for path_type in relaxed:
        path_type.exists = False
    try:
        yield
    finally:
        for path_type in relaxed:
            path_type.exists = True


def _invoke(args: list[str]) -> tuple[int, str]:
    """Run `marketforge ARGS` in this process; return (exit code, output)."""
    import click

    from marketforge.cli.main import cli

    out = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            # Outside standalone mode, click RETURNS the code of a ctx.exit()
            # (how every subcommand reports failure) instead of raising.
            returned = cli.main(args=args, prog_name="marketforge", standalone_mode=False)
            if isinstance(returned, int) and not isinstance(returned, bool):
                code = returned
        except click.exceptions.Exit as e:
            code = e.exit_code
        except click.ClickException as e:
            e.show(file=out)
            code = e.exit_code
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return code, out.getvalue()


def check_command(command: Command) -> None:
    """Check a `marketforge` command without running it."""
    from marketforge.cli.main import cli

    rest = list(command.args)
    while rest and rest[0].startswith("-"):  # the group's own flags: --debug, --version
        rest.pop(0)
    if not rest:
        code, out = _invoke(command.args)
        if code:
            raise ExampleError(
                command.line, f"`marketforge {shlex.join(command.args)}` failed: {out}"
            )
        return
    name, args = rest[0], rest[1:]
    subcommand = cli.commands.get(name)
    if subcommand is None:
        raise ExampleError(command.line, f"`marketforge {name}`: no such command")
    # A dry run reads the override file; one the reader provides cannot exist here,
    # so such an example is only parsed.
    config = args[args.index("--config") + 1] if "--config" in args[:-1] else None
    if name == "generate" and "--dry-run" not in args and (config is None or Path(config).exists()):
        code, out = _invoke([*command.args, "--dry-run"])
        if code:
            raise ExampleError(
                command.line, f"`marketforge {shlex.join(command.args)}` is refused: {out.strip()}"
            )
        return
    import click

    with _paths_need_not_exist(subcommand):
        try:
            subcommand.make_context(name, args)
        except click.exceptions.Exit:
            pass
        except click.ClickException as e:
            raise ExampleError(
                command.line, f"`marketforge {shlex.join(command.args)}`: {e.format_message()}"
            ) from e


def run_command(command: Command) -> None:
    code, out = _invoke(command.args)
    if code:
        raise ExampleError(
            command.line,
            f"`marketforge {shlex.join(command.args)}` exited with {code}: {out.strip()[-2000:]}",
        )


def check_toml(block: Block, workdir: Path) -> None:
    try:
        tomllib.loads(block.code)
    except tomllib.TOMLDecodeError as e:
        raise ExampleError(block.line, f"invalid TOML: {e}") from e
    first = block.code.strip().splitlines()[0] if block.code.strip() else ""
    named = TOML_NAME.match(first)
    target = workdir / (named["name"] if named else ".example.toml")
    target.write_text(block.code, encoding="utf-8")
    try:
        _public_api().instruments(overrides=str(target))
    except Exception as e:
        raise ExampleError(block.line, f"not a valid override file: {e}") from e
    finally:
        if not named:
            target.unlink()


def run_python(block: Block, namespace: dict[str, Any]) -> None:
    # Padding puts the block at its own lines, so a traceback names the page's line.
    code = compile("\n" * (block.line - 1) + block.code, str(block.path), "exec")
    try:
        exec(code, namespace)
    except Exception as e:
        frames = [f for f in traceback.extract_tb(e.__traceback__) if f.filename == str(block.path)]
        line = frames[-1].lineno if frames and frames[-1].lineno else block.line
        raise ExampleError(line, f"{type(e).__name__}: {e}") from e


# --------------------------------------------------------------- the pages


@contextlib.contextmanager
def _working_directory(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def check_page(path: Path, report: Report) -> None:
    rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    try:
        blocks = extract_blocks(rel, path.read_text(encoding="utf-8"))
    except ExampleError as e:
        report.errors.append((rel, e.line, str(e)))
        return
    if not blocks:
        return
    namespace: dict[str, Any] = {"__name__": "__doc_example__"}
    exec("import marketforge as mf", namespace)
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmp, _working_directory(Path(tmp)):
        for block in blocks:
            report.checked[block.mode] += 1
            if block.mode == "none":
                continue
            try:
                if block.mode == "signature":
                    check_signature(block)
                elif block.language == "toml":
                    check_toml(block, Path(tmp))
                elif block.language == "python":
                    check_python_api(block)
                    if block.mode == "run":
                        run_python(block, namespace)
                else:
                    commands = shell_commands(block, substitute=block.mode == "static")
                    for command in commands:
                        check_command(command)
                    if block.mode == "run":
                        for command in commands:
                            run_command(command)
            except ExampleError as e:
                report.errors.append((rel, e.line, str(e)))
    print(f"{rel}: {len(blocks)} block(s) in {time.perf_counter() - started:.1f} s", flush=True)


def documentation_pages(root: Path) -> list[Path]:
    tracked = subprocess.run(
        ["git", "ls-files", "--", *DOC_GLOBS],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    return [root / name for name in sorted(tracked)]


def _summary(markdown: str) -> None:
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(markdown + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="*", type=Path, help="pages to check (default: all)")
    args = parser.parse_args(argv)

    os.environ.setdefault("TQDM_DISABLE", "1")
    mf = _public_api()
    origin = Path(mf.__file__).resolve()
    if "site-packages" not in origin.parts:
        print(f"::warning::checking against {origin}, not an installed package")

    pages = [p.resolve() for p in args.files] or documentation_pages(ROOT)
    report = Report()
    for page in pages:
        check_page(page, report)

    counts = ", ".join(f"{n} {mode}" for mode, n in report.checked.items() if n)
    for path, line, message in report.errors:
        flat = message.replace("\n", " ")
        print(f"::error file={path.as_posix()},line={line},title=Documentation example::{flat}")
    if report.errors:
        _summary(
            f"### Documentation examples: {len(report.errors)} broken\n\n"
            + "\n".join(f"- `{p.as_posix()}:{line}`: {m}" for p, line, m in report.errors)
        )
        print(f"{len(report.errors)} broken example(s) in {len(pages)} page(s) ({counts})")
        return 1
    _summary(f"### Documentation examples: all work\n\n{len(pages)} pages: {counts}.")
    print(f"All examples work: {len(pages)} page(s), blocks: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
