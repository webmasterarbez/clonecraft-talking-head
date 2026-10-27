"""Rules a check can state exactly. The commit hook and CI run them as part of pytest.

Judgement calls live in CODING_STANDARDS.md; these are the rules that do not need one.
"""

from __future__ import annotations

import ast
import collections
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODE = [path for folder in ("src", "tests", "scripts") for path in sorted((ROOT / folder).rglob("*.py"))]
SUBPROCESS_CALLS = {"run", "Popen", "check_output", "check_call", "call"}


def _subprocess_calls(path: Path) -> list[ast.Call]:
    return [
        node for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subprocess"
        and node.func.attr in SUBPROCESS_CALLS
    ]


def test_every_subprocess_call_says_where_its_stdin_comes_from() -> None:
    missing = [
        f"{path.relative_to(ROOT)}:{call.lineno} subprocess.{call.func.attr}"  # type: ignore[attr-defined]
        for path in CODE
        for call in _subprocess_calls(path)
        if not any(keyword.arg == "stdin" for keyword in call.keywords)
    ]
    assert not missing, (
        "pass stdin= to each subprocess call: subprocess.DEVNULL, or PIPE when the child reads it. A child that "
        "inherits the terminal's stdin can block for good. Missing at: " + "; ".join(missing)
    )


def test_a_named_constant_with_one_value_is_defined_in_one_module_only() -> None:
    """A constant name defined in two modules with the same value is one fact in two places (CODING_STANDARDS).

    Different names that happen to share a value, and one name with a different value per engine, are different
    facts, so they are not compared.
    """
    owners: dict[tuple[str, str], set[str]] = collections.defaultdict(set)
    for path in sorted((ROOT / "src" / "clonecraft").glob("*.py")):
        for node in ast.parse(path.read_text()).body:
            if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
                continue
            target = node.targets[0]
            if not (isinstance(target, ast.Name) and target.id.isupper()):
                continue
            try:
                ast.literal_eval(node.value)
            except ValueError:
                continue  # computed values are not compared
            owners[(target.id, ast.unparse(node.value))].add(path.name)
    shared = {f"{name} = {value}": sorted(modules) for (name, value), modules in owners.items() if len(modules) > 1}
    assert not shared, f"a constant with one value is defined in more than one module: {shared}"


def test_pyflakes_finds_nothing_to_fix() -> None:
    ruff = shutil.which("ruff")
    assert ruff, "ruff is not on PATH; run `uv sync` so the dev dependency is installed"
    result = subprocess.run(
        [ruff, "check", "--select", "F", "--no-cache", "src", "tests", "scripts"],
        cwd=ROOT, capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )
    assert result.returncode == 0, result.stdout + result.stderr
