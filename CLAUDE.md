# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# CloneCraft

Turns a finished Script into a talking-head Video of a Persona, entirely on this
machine (ADR 0001). Use the terms in `GLOSSARY.md` (Persona, Channel, Script,
Delivery Cue, Voice Reference, Voiceover, Video, Operator) in code, tests,
issues and messages.

## Scope: this codebase only

This repository is the single source of truth. Work from what exists inside
this repository; when something you need is not here,
say so and ask.

- **Memory.** Each session starts from the repo's files. Persistent memory
  (`~/.claude/projects/*/memory/`, `MEMORY.md`) stays unread and unwritten.
- **Skills, plugins, agents.** Use those under this repo's `.claude/`. When a
  plugin ships a skill with the same name as a repo skill (for example
  `mattpocock-skills:implement` and `implement`), run the repo one.
- **Instructions.** This file and other `CLAUDE.md` files inside the repo.
- **References.** Cite and build on code, docs and configs in this codebase.
- **External services.** MCP servers, connectors and web lookups are for requests
  that ask for them.

If the answer is not in the repo files, tell the user it isn't in the codebase.

## Commands

```sh
uv sync                                    # main env (Python 3.12+, numpy, pyyaml)
uv run mypy                                # strict, over src/ and tests/
uv run pytest -q -n auto                   # whole suite; needs ffmpeg on PATH
uv run pytest tests/test_voiceover.py -k cue   # one file / one test
uv run python scripts/mutate.py [-k <expr>] <tests> <source> '<find>' '<replace>' ...   # prove a test can fail; -k runs only the selected tests

uv run clonecraft voiceover <platform>/@<handle> <script>   # Channels: ls platform/*/channels; paths and Formats: docs/operator-guide.md
uv run clonecraft video <platform>/@<handle> <script> [--format 16:9]
uv run clonecraft models [--fix]           # check models/ against config/models.toml (sha256)
sh scripts/install-voice-engine.sh         # VoxCPM2 into vendor/voice-env (separate Python 3.14 + CUDA torch)
```

The gate is mypy and pytest. pytest also holds the rules a check can state, in
`tests/test_repo_rules.py` (ruff's pyflakes rules, one value per constant, stdin on every
subprocess call). There is no formatter. They run unattended in about 20 s with no GPU,
models or network, so run both after every change. `voiceover`, `video`, `models --fix` and the install script are
different: they use the GPU, ask the Operator questions, call sudo or
download up to 38 GB. Run them only when asked.

## Docs

`README.md`, `docs/operator-guide.md` and `docs/setup-and-maintenance.md` are written for the Operator. When you change a command, a prompt, an error message, a file layout or an install step, update them in the same change. Their examples use made-up names, never a real Persona or Channel.

## Checks

Review reads `CODING_STANDARDS.md`. Enable the commit hook once per clone with
`git config core.hooksPath .githooks`; it runs mypy and pytest, as does CI.

## Architecture

The module map, the on-disk layout and the paths through the code (Slide cards, the Voiceover, the Video, the models) are in `docs/architecture.md`. Read it before changing how the pieces connect.

## Gotchas

- `persona/` and `platform/` hold a real person's face, voice and Scripts. They
  are git-ignored and must never be committed, uploaded or copied out of the
  repo. Tests build their own layout in `tmp_path`.
- `scripts/voxcpm_worker.py` runs under `vendor/voice-env`, not the main
  environment. It cannot import `clonecraft` and is outside mypy's `files`.
  Its JSON protocol is defined in its docstring, and `tests/fake_worker.py`
  must match it.
- Test names are full sentences (`test_a_cue_is_not_sent_when_there_is_a_transcript_…`).
  Error messages are written for the Operator and name the file or program
  at fault.

## Agent skills

### Issue tracker

Issues and specs live in GitHub Issues on webmasterarbez/clonecraft-talking-head, used through the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default labels: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
