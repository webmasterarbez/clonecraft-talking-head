---
name: pr-checks-stuck-triage
description: Use when a PR check is stuck or gh run rerun fails.
category: git-workflow
---

# Find the step a stuck PR check is on, then let the user choose the fix

A check that runs far past its usual time is a hang to diagnose, not a wait to repeat. Find the step first, then act only on what the user approves.

1. Read the checks by job step, not the summary: `gh pr checks N` gives the run ids, then `gh run view RUN --json jobs --jq '.jobs[]|"\(.name) \(.status) " + ([.steps[]?|select(.status=="in_progress")|.name]|join(","))'`. A job stuck on `sudo apt-get update && sudo apt-get install -y ffmpeg` for 15 minutes or more is a runner or mirror hang; the code under test has not run.
2. `gh run cancel` returns before the run stops, so a cancelled run can show in_progress for minutes. Re-read its status after a wait; do not treat the cancel's exit code as proof.
3. `gh run rerun` can refuse with "cannot be rerun; its workflow file may be broken". The refusal alone does not show the workflow is broken, so do not edit the workflow to chase it.
4. Re-triggering with an empty commit adds a commit to the PR. Ask the user first, and never force-push to re-trigger.
5. Name the durable fix in the report and let the user choose it, such as `timeout-minutes:` on the job so a hung install fails fast, or a cached or pinned ffmpeg. Do not implement it unasked. Once the user approves, guard the install so it runs only when the tool is missing: `- run: command -v ffmpeg || (sudo apt-get update && sudo apt-get install -y ffmpeg)`. In this repo that guard cleared the hang: the run that had sat on the install passed within about five minutes after the change.
6. Read the merge state correctly: `UNSTABLE` means a check is not green; `DIRTY` means the branch conflicts with its base, and the merge steps are in git-commit-explicit-paths. Never merge while a required check is pending. Each push runs the checks twice (push and pull_request events), so a cancelled duplicate stays listed beside the passing run and can keep the state at `UNSTABLE`. Read the conclusion of each run on the head commit before merging, and name the cancelled duplicate in the report.
7. Wait on checks with a Monitor until-loop, as in the waiting section of `media-render-verification`, never a sleep chain.
