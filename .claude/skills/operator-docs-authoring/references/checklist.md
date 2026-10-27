# Operator docs checklist

1. Read the code path for each claim: `src/clonecraft/cli.py` for commands and errors, `project.py` for the layout, `handoff.py` and `face.py` for GPU and face-engine figures, the install scripts for install steps, and the ADR named in the text.
2. Run `sh .claude/skills/operator-docs-authoring/scripts/check-docs.sh`. It prints `docs ok` only when there are no leak hits and no broken relative links.
3. Re-read every "see section N" reference against the target heading.
4. Run `uv run mypy` and `uv run pytest -q -n auto`.
5. Stage the docs by path and check `git diff --cached --stat` before committing (git-commit-explicit-paths).
6. Before reporting, run `git status --short` again. Say which code the docs depend on and whether it is committed.
