---
name: voiceover-gpu-memory-budget
description: Use when setting GPU memory budgets for Voiceover or Video.
category: video-production
---

# Set a GPU memory budget from a measured peak, then change every copy of it

A budget figure is a claim about this card. Measure the peak here before setting it, and when it changes, change every place that states it in the same change.

- Measure first: run one step with `nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -l 1` alongside it, take the idle reading before the step, and use the maximum above idle. A quoted figure is an estimate until measured.
- Set the MiB figure (`VOICEOVER_NEEDED_MIB`) to the measured peak plus margin, and write the GiB form beside it (8704 MiB is 8.5 GiB). `NEEDED_MIB` is the Video budget and is a separate figure; do not move it with the Voiceover one.
- Find every copy by grepping the old figure in both forms (`10.5 GB`, `10500`, `10500 MiB`) across `src/`, `scripts/`, `tests/` and `docs/`. The worker sits outside mypy, so grep it too. Update each site listed in `references/gpu-budget-sites.md`.
- A test fixture whose comment does the arithmetic (`# 12000 - 1200 - 2000 = 8800 MiB free`) must be recomputed when the threshold moves, so it still lands on the side its name says.
- Record a measured figure as a dated amendment section in the ADR, not by rewording the decision. ADR 0005 keeps its amendment below its decision.
- Before a real Voiceover run, copy the approved `script-NN.wav`, `script-NN.words.json` and `script-NN.spoken.sha256` into the session scratchpad and note their `sha256sum`. The run overwrites them.
- Gate with `uv run mypy` and `uv run pytest -q -n auto`. Run the GPU step only when the Operator asks.
- A refusal reading `only N MiB of GPU memory is free ... Still holding memory: python (M MiB)` names a process on the card. Identify it with `nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv`. If it belongs to another session, do not stop it: wait on its PID as the waiting section of `media-render-verification` describes, then run again.

Sites that state the Voiceover figure: `references/gpu-budget-sites.md`.
