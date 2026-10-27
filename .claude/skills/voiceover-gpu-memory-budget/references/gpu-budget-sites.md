# Where the Voiceover and Video GPU figures are stated (measured 2026-10-26)

Measured on the RTX 5070 (12 GB) with the desktop idle beforehand: VoxCPM2 alone about 5.3 GB; the int8 faster-whisper large-v3-turbo transcriber (run on `cuda`) about 1 GB more; peak about 7.4 GB above idle. Voiceover threshold: 8704 MiB (8.5 GiB). The Video figure `NEEDED_MIB` (10,000 MiB) was not re-measured.

Sites for the Voiceover figure:

- `src/clonecraft/handoff.py`: `VOICEOVER_NEEDED_MIB`.
- `scripts/voxcpm_worker.py`: `NEEDED_GIB`, must match. Outside mypy.
- `tests/fake_worker.py`: mirrors the worker's refusal text.
- `tests/test_voiceover.py` and `tests/test_voxcpm_engine.py`: the GB figure in the `NotEnoughGpuMemory` message and its assertion.
- `tests/test_gpu_handoff.py`: the MiB figure in the assertion, and fixture comments that do the arithmetic.
- `tests/test_slide_cards.py`: fixture comment that does the arithmetic.
- `docs/operator-guide.md`: section 4 prose, and the error-table row that quotes `needs about 8704 MiB`.
- `docs/setup-and-maintenance.md`: section 4 prose and the `VOICEOVER_NEEDED_MIB` mention.
- `docs/adr/0003-video-step-takes-the-whole-gpu.md`: "The Voiceover step (about 8.5 GB)".
- `docs/adr/0005-match-the-approved-voice-pipeline.md`: the memory line, plus its measured amendment.
