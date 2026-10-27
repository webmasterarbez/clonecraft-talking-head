---
name: operator-docs-authoring
description: Use when editing CloneCraft README, operator or setup docs.
category: documentation
---

# Operator docs: write from source, keep them in step with the code

Every claim in the README and the two guides in `docs/` comes from the code, tests, install scripts or an ADR you have read in this session. Update the docs in the same change as any command, prompt, error message, file layout or install step (CLAUDE.md "Docs").

- **Verify before writing.** Check each command, file name, error string and number against `src/clonecraft/`, `config/`, the install scripts and the cited ADR. Cite the ADR by number instead of restating its reasoning. Name functions and modules as the code defines them (`captions.ass_script`, not the shorter name you remember). State a condition the way the code tests it, in operator terms: a Video uses a Brand pack when its Script has a slides list, even one of face entries only, or a hook. "Has a Slide card or a hook" was wrong and had to be corrected in three files.
- **Made-up names only.** Use `example`, `@examplechannel`, `script-01`. Never a real Persona or Channel name, and never a home-directory path. Run `sh .claude/skills/operator-docs-authoring/scripts/check-docs.sh` from the repo root; it flags leaks and broken relative links. The leak check also matches any `@` followed by a letter, so a CSS at-rule such as `@media` fails it even inside a code block; describe the rule in words instead (for example, "a media query for a window at least as wide as it is tall").
- **Label invented values.** Sample output, candidate start times and counts are marked as examples. Report measured figures only, and say what they were measured on.
- **Prerequisites go everywhere.** When a feature makes a program, setting or model necessary for some Scripts, grep README, `docs/setup-and-maintenance.md` and `docs/operator-guide.md` for the old wording (`Only Scripts with`, `need it`, the program's name) and update every hit in the same change. Making Chrome needed for hooks left the README and the setup guide saying only Slide cards needed it. Removing a feature reverses this: delete the prerequisite only it needed (the setup guide's ffmpeg row once named libass for the `subtitles` filter, which only captions used), and grep the removed feature's name in the same files.
- **Error tables quote the code.** Copy each message from the string the code raises (grep its first words) and keep all of it inside the backticks, including the tail after the first clause. Put explanations outside the backticks, never inside them.
- **Cross-references.** The script cannot check "see section N" text. After renumbering or adding a section, re-read the target heading.
- **Gate before commit.** Docs-only changes still run `uv run mypy` and `uv run pytest -q -n auto` (CLAUDE.md). Run them before the commit, not after.
- **Do not claim the docs match the code** until the code they describe is committed. Check `git status --short` for uncommitted code the docs depend on, and say so if it is uncommitted.
- **Progress and verification lines go stale.** When a feature's scope grows or ships, grep README, the operator guide, the setup guide, CLAUDE.md, the ADRs and GLOSSARY.md for `yet`, `not made`, `for now`, `so far`, `only in`, `refused`, `issue #`, `checked on this machine`, `left for later`, `not added`, `does not cover` and `no <feature>` lines (for example `no captions`). A shipped feature leaves its deferral lines behind in all of those files: when captions shipped, ADR 0007 still said captions were "left for later", the operator guide still said "Captions, b-roll and music are not added", and GLOSSARY still said the hook "has no captions". Rewrite each one in the same change. A feature widened to a new Format or case leaves these behind: "Slide cards are made only in 9:16 so far; a 16:9 Format with a slides list is refused" went stale once 16:9 cards shipped. Restate each hit with what was actually run (the test suite, or a real run on this machine) and what has not been run.

Details and the leak patterns: [references/checklist.md](references/checklist.md).
