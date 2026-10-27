# Coding standards

Read at review. `mypy --strict` and `pytest` already run in `.githooks/pre-commit` and CI; this file holds what they cannot check. Rules a check can state exactly are tests in `tests/test_repo_rules.py`: add a new mechanical rule there, not here. Terms follow `GLOSSARY.md`.

- **Tests enter at the CLI.** Call `main(argv, root=..., voice_engine=..., face_engine=..., gpu=..., ask=...)` and assert on files written, text printed and requests made. Fakes stand in only for things outside the repo: the engines, the GPU, the Operator's answers, `nvidia-smi` and `sudo` on PATH, a `file://` download source. ffmpeg runs for real on tiny clips.
- **Expected values are worked arithmetic.** Write each as a sum in the test comment (`0.5 s + 0.2 s tail + 0.06 s padding`), never as a number copied from the output. The assert uses the number the comment works out. If it must be looser, the comment says why.
- **A new test must be able to fail.** Before committing, break the code under test on purpose and see the test go red: `uv run python scripts/mutate.py [-k <expr>] <tests> <source> '<find>' '<replace>' ...`. A survivor means a weak test or dead code, or a limit that the commit body must name. The commit body lists the mutants run and CAUGHT or SURVIVED for each.
- **Bad input ends in one line.** A missing file, a malformed config, an unusable answer or an engine failure prints `clonecraft: <what and where>` to stderr and returns 1. Wherever the code reads outside input or a prompt, handle empty input, `EOFError`, Ctrl-C and look-alike characters (`"²".isdigit()` is true).
- **Name the offender.** An error names the Channel, Script, Persona, file or program at fault.
- **Validate before acting.** Check every input before asking the Operator anything, stopping anything or spending GPU time.
- **One source for each fact.** A threshold, path or rule lives in one constant or ADR; skills and other docs point to it. `tests/test_repo_rules.py` fails when a constant name with one value is defined in two modules.
