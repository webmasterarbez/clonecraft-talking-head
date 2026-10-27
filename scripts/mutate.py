"""Check that tests can fail: apply each deliberate break to a throwaway copy of the repo and run the tests there.

    uv run python scripts/mutate.py tests/test_gpu_handoff.py src/clonecraft/handoff.py \
        'MIN_PROGRAM_MIB = 100' 'MIN_PROGRAM_MIB = 101'  'if free < needed_mib:' 'if False:'

After the test path and the source file, each pair of arguments is one mutant: text to find, text to put in
its place. Prints CAUGHT when the tests fail and SURVIVED when they still pass. The working tree is never changed.

Options, before the test path:
    -k EXPR   run only the tests pytest's -k selects, such as -k "cut_in or hook"

The repo is copied once when the run starts, so editing files while it runs does not change later mutants.
Each result line is printed as soon as it is known.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COPIED = ("src", "tests", "pyproject.toml", "scripts", "config")
NO_TESTS_SELECTED = 5  # pytest's exit code when -k selects nothing


def _copy_repo(into: Path) -> None:
    for name in COPIED:
        if (ROOT / name).is_dir():
            shutil.copytree(ROOT / name, into / name, ignore=shutil.ignore_patterns("__pycache__"))
        elif (ROOT / name).is_file():
            shutil.copy(ROOT / name, into / name)


def main(argv: list[str]) -> int:
    select = None
    if len(argv) >= 2 and argv[0] == "-k":
        select, argv = argv[1], argv[2:]
    if len(argv) < 4 or len(argv) % 2:
        print(__doc__)
        return 2
    tests, source, pairs = argv[0], argv[1], list(zip(argv[2::2], argv[3::2], strict=True))
    survivors = 0
    with tempfile.TemporaryDirectory() as snapshot_dir:
        snapshot = Path(snapshot_dir)
        _copy_repo(snapshot)
        for find, replace in pairs:
            with tempfile.TemporaryDirectory() as scratch:
                copy = Path(scratch)
                _copy_repo(copy)
                target = copy / source
                text = target.read_text()
                if find not in text:
                    print(f"NOT APPLIED  {find!r} is not in {source}", flush=True)
                    survivors += 1
                    continue
                target.write_text(text.replace(find, replace, 1))
                env = {**os.environ, "PYTHONPATH": str(copy / "src")}
                command = [sys.executable, "-m", "pytest", tests, "-q", "-x", "-p", "no:cacheprovider"]
                if select:
                    command += ["-k", select]
                result = subprocess.run(
                    command, cwd=copy, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                )
                if result.returncode == NO_TESTS_SELECTED:
                    print(f"NO TESTS  -k {select!r} selects nothing in {tests}", flush=True)
                    return 2
                caught = result.returncode != 0
                survivors += not caught
                print(f"{'CAUGHT  ' if caught else 'SURVIVED'}  {find!r} -> {replace!r}", flush=True)
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
