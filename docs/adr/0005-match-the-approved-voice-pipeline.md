# Match the earlier project's voice pipeline

The first full Voiceover made with the settings tuned by ear in ADR 0004 had odd pauses, and the voice changed from one piece to the next. Measuring two runs showed why. Every piece is an independent random draw: neighbouring pieces jumped up to 3.6 semitones in pitch, and pace ranged from 163 to 252 words a minute. The 37 s sample those settings were chosen from was a single seeded draw of five pieces. The voice the Operator approved came from the earlier project, so CloneCraft now copies that project's pipeline exactly, as a baseline to tune from. This supersedes ADR 0004's tuned settings and its "no automatic speech check" line.

- **Packages.** `config/voice-requirements.txt` is the lock file of the earlier voice pipeline, copied once. `scripts/install-voice-engine.sh` installs exactly that, with `uv pip sync`. torch and torchaudio arrive as `2.10.0+cu128`, the same build the earlier project runs.
- **Speech.** The worker does ultimate cloning as in ADR 0004, with `cfg_value` 2.0, the denoiser off, no seed, and VoxCPM's default 10 diffusion steps.
- **Chunking.** Whole sentences are packed into pieces of at most 18 words, and a paragraph break ends a piece (`CHUNK_WORDS` in `script.py`).
- **Joining** (`audio.py`):
  - Take edges quieter than −45 dB are cut (`EDGE_DB`).
  - Pauses inside a take quieter than −50 dB are shortened to 0.4 s (`PAUSE_DB`, `JOIN_PAUSE_S`).
  - Takes fade in and out over 10 ms.
  - Each join lasts 0.4 s.
- **Speech Check** (`speechcheck.py`). After each take, faster-whisper large-v3-turbo (GPU, int8, word timestamps) transcribes it. See the amendment below. The score blends word and letter accuracy, with the transcriber's digits spelled out first.

  | Score | What happens |
  |---|---|
  | 92 or more | The take passes. |
  | 85 up to 92 | The take is kept and flagged, and one more take is tried. |
  | Under 85 | A new take is tried, up to three in all. The best one scoring 85 or more is kept. Otherwise the run stops, names the piece, and writes no Voiceover. |

  Unheard audio after the last matched word is handled by length. From 0.5 s to 1.0 s, it is cut where the first 0.1 s of quiet begins. Over 1.0 s, the take counts as bad.
- **Quirks kept on purpose:**
  - After two takes in the middle band, the later one is kept even when the first scored higher.
  - A best take kept after three tries is used without its trailing cut.
- **Left out.** The earlier project's speaker match always reported a match, so it is left out. The earlier project ran a new process for each take; CloneCraft keeps one worker with the model loaded. If the voice still differs from the approved one, one process per take is the next thing to test.
- **Belongs to the Video step.** The final mix's −14 LUFS loudness and its 0.4 s fade-out happen there, not in the Voiceover.

The Operator still listens to the whole Voiceover before any Video is made.

## Amendment (2026-10-26): the speech check transcribes on the GPU

The speech check's faster-whisper large-v3-turbo moved from the CPU to the GPU (`device="cuda"`, still int8, word timestamps). Its JSON protocol and the score thresholds are unchanged. The thresholds were copied from the earlier project, not tuned here, so the GPU transcription has to keep the same pass rates on the same Script before it is kept. The Voiceover now needs about 8.5 GB of free GPU memory (`VOICEOVER_NEEDED_MIB`, 8704 MiB), up from 8 GB. Measured on the RTX 5070 on 2026-10-26, VoxCPM2 and the transcriber together peaked at about 7.4 GB above the desktop's idle use, and the transcriber alone added about 1 GB. The VoxCPM2 settings above are unchanged.
