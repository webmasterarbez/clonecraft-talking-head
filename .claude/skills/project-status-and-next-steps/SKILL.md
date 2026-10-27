---
name: project-status-and-next-steps
description: Use when asked for project status or what needs doing next.
category: planning
---

# Project status and next steps

Answer status and next-step questions from the repo's own state, in this order, and report only what you actually checked.

1. **Git state.** Run `git status --short`, `git branch --show-current`, `git log --oneline -15`, `git status -sb`, and `git rev-list --left-right --count origin/main...HEAD`. Report commits ahead of the upstream separately from commits not yet on main. Flag uncommitted files that are not product code, and do not commit them.
2. **Open work.** Run `gh issue list --state open --limit 50`, then `gh issue view N --json body` for the parent PRD and for any issue whose state is unclear. Group by the triage labels in `docs/agents/triage-labels.md`.
3. **What is buildable.** Read each open issue's `Blocked by:` line. An issue is ready only when every blocker is closed, or is built in code on the current branch and awaiting merge.
4. **Decisions.** When a next step depends on a design choice, check the ADR titles in `docs/adr/` and read the relevant one.
5. **Gate.** Run the project's gate from its CLAUDE.md Commands section and report the result. For CloneCraft that is `uv run mypy` and `uv run pytest -q -n auto`. Do not run GPU, voiceover, video or models commands for a status check.
6. **Report** in three blocks: built but not yet closed (close once merged and its acceptance criteria are checked), open and ready, and needs a human. Name any check that lives outside the repo, such as an Operator's review, instead of guessing whether it is done.
7. **Outward actions** such as push, PR, issue close or merge are offered as next steps, not performed, unless the user asks. A reply that picks your numbered steps ("do 1 2", "1 and 2", "do it") is that ask: perform the picked steps in that turn, read back each result, and stop only at a step the permission layer denies. Do not re-offer the same choice a second time. Before closing an issue, read its body: CloneCraft issues carry a `## Testing Decisions` section and no acceptance checklist, so say the checklist is absent and check that section instead.
