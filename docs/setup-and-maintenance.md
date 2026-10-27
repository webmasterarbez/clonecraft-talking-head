# Setup and maintenance

This guide is for the Operator when installing CloneCraft, checking it, changing what it is built from, or fixing it. For making a Voiceover or a Video, see [operator-guide.md](operator-guide.md). Capitalised terms are defined in [GLOSSARY.md](../GLOSSARY.md).

Run every command from the repo root.

## 1. What the machine needs

| Need | Why |
|---|---|
| Linux, with an NVIDIA GPU of at least 12 GB and its driver | The only tested setup is an RTX 5070 (12 GB, Blackwell). Nothing else is supported. |
| `nvidia-smi` on the PATH | Lists GPU programs and free memory for the Video step. |
| `uv` | Manages the main environment and both engine environments. |
| `git` | The face-engine install clones four repos. |
| `ffmpeg` and `ffprobe` on the PATH | Decode audio, crop the Likeness and assemble the Video. The test suite also needs ffmpeg. |
| Google Chrome (`google-chrome` on the PATH) | Draws Slide cards and the hook in headless mode, without the GPU. Only Scripts with a slides list or a hook need it. |
| The CUDA toolkit 12.8 or later (`CUDA_HOME`, default `/usr/local/cuda`) | Only to compile SageAttention during the face-engine install. |
| About 38 GB free for `models/`, plus space for the engine environments in `vendor/` | Model weights and the two Python environments. |
| `sudo` that does not ask for a password, for `systemctl` | Only if you want the Video step to stop and restart system services. See section 4. |

## 2. Install

CloneCraft is one repo, but the work is done by two engines that each live in their own environment under `vendor/` (git-ignored), plus model files in `models/` (git-ignored).

| Part | Where it lives | Made by |
|---|---|---|
| CloneCraft itself (Python 3.12+, numpy, pyyaml) | `.venv/` | `uv sync` |
| Voice engine: VoxCPM2 and faster-whisper (Python 3.14, CUDA torch) | `vendor/voice-env/` | `sh scripts/install-voice-engine.sh` |
| Face engine: InfiniteTalk run by ComfyUI (Python 3.12, CUDA torch) | `vendor/face-env/`, `vendor/ComfyUI/`, `vendor/SageAttention/`, `vendor/wheels/` | `sh scripts/install-face-engine.sh` |
| Model files | `models/` | `uv run clonecraft models --fix` |

Do these in order.

```sh
uv sync
sh scripts/install-voice-engine.sh
sh scripts/install-face-engine.sh
uv run clonecraft models --fix
```

- **Voice engine script.** Creates `vendor/voice-env` and installs exactly the packages in `config/voice-requirements.txt`, then checks it can import `voxcpm` and `faster_whisper`.
- **Face engine script.** Clones ComfyUI, ComfyUI-WanVideoWrapper, ComfyUI-VideoHelperSuite and SageAttention at pinned commits; applies two patches from `config/`; builds a wheel of SageAttention once into `vendor/wheels/` (this is the slow, CUDA-dependent step); installs exactly `config/face-requirements.txt`; then checks that torch sees the GPU. `TORCH_CUDA_ARCH_LIST` defaults to `12.0` (the RTX 5070); set it for a different card, and set `CUDA_HOME` if CUDA is not in `/usr/local/cuda`.
- **Models.** `config/models.toml` lists every file with its path, size, sha256 and download URL. `models --fix` downloads what is missing or wrong, then checks again. It is large (about 38 GB), so expect a long download.
- Both install scripts can be run again safely; they bring the environment back to the recorded pins.

Install the engines only when you can leave the machine for a while: they download a lot, compile code, and use the GPU. CloneCraft's own tests do not need any of this.

### Checking the install

```sh
uv run clonecraft models
```

Each model file prints a line: `OK <path>`, or `MISSING`, `WRONG SIZE (…)` or `WRONG CONTENT` followed by the path. The command ends with `all N model files are good`, or `N of M model files need attention` and exit code 1. Run it with `--fix` to repair, and it re-checks afterwards. A download that still fails its check is not kept and is reported as an error.

If a Voiceover or Video command says an engine is not installed, it lists what is missing and tells you which script to run.

## 3. Where things are

```
config/
  models.toml                  every model file: path, size, sha256, URL
  voice-requirements.txt       the voice engine's exact packages
  face-requirements.txt        the face engine's exact packages
  face-wav2vec2.patch          patch for ComfyUI-WanVideoWrapper under transformers 5.x
  sageattention-cxx20.patch    patch to build SageAttention against torch 2.14
  infinitetalk-graph.json      the recorded InfiniteTalk graph and settings
  brand-pack-starter/          a Brand pack to copy into persona/<name>/brand-packs/ (from the approved look)
scripts/
  install-voice-engine.sh
  install-face-engine.sh
  voxcpm_worker.py             runs inside vendor/voice-env; talks JSON over stdin/stdout
  mutate.py                    proves a test can fail
vendor/                        engines and their environments (git-ignored)
models/                        model files (git-ignored)
persona/  platform/            your personal content (git-ignored)
settings.local.yaml            your saved GPU answers (git-ignored)
```

Nothing in `vendor/`, `models/`, `persona/`, `platform/` or `settings.local.yaml` is committed. After a fresh clone, the install steps in section 2 rebuild the first two; the last three are yours.

## 4. The Video step and the GPU

The Video step needs about 10,000 MiB of free GPU memory (`NEEDED_MIB` in `src/clonecraft/handoff.py`) and asks the Operator before stopping anything (ADR 0003). The Voiceover step needs about 8.5 GB (`VOICEOVER_NEEDED_MIB`) and uses the same flow, but only when less than that is free.

- Programs holding at least 100 MiB of GPU *compute* memory are listed (`MIN_PROGRAM_MIB`). Graphics processes (the compositor, desktop shell, Electron or Chromium-style windows) are not stopped by CloneCraft, so when the free figure is still short, close those applications yourself. Do not close the compositor or the shell.
- System services are stopped and started with `sudo -n systemctl`. User services are treated as plain programs and only stopped, by SIGTERM, waiting up to 20 s.
- A service goes on the restart list before it is stopped, so a stop that fails halfway is still undone.
- Answers are saved in `settings.local.yaml`:

  ```yaml
  gpu:
    example-service.service:
      restart: true
      stop: true
  ```

  Edit or delete entries to change an answer. Delete the file to be asked everything again. A damaged file stops the step with a message naming it.
- For a service to be restartable without typing a password, `sudo -n systemctl stop <unit>` and `sudo -n systemctl start <unit>` must work non-interactively for your user. Add a narrow `sudoers` rule for those units only; do not grant blanket sudo.

## 5. Updating and changing what it is built from

Everything is pinned so the machine can be rebuilt from the repo. Change a pin deliberately, then check the result by making a short test render before relying on it.

| To change | Edit | Then |
|---|---|---|
| Voice engine packages | `config/voice-requirements.txt` | `sh scripts/install-voice-engine.sh` |
| Face engine packages | `config/face-requirements.txt` | `sh scripts/install-face-engine.sh` |
| A ComfyUI, node pack or SageAttention commit | the `pinned` lines in `scripts/install-face-engine.sh`; check that the two patches in `config/` still apply | `sh scripts/install-face-engine.sh` |
| A model file | its entry in `config/models.toml` (path, size, sha256, URL) | `uv run clonecraft models --fix` |
| The face engine's graph or settings | `config/infinitetalk-graph.json` | render a short test |

Tuning constants were copied from the earlier project's approved pipeline or measured on this machine's 12 GB RTX 5070, and their reasons are in the ADRs: `CHUNK_WORDS` (`script.py`), `JOIN_PAUSE_S`, `PAUSE_DB`, `EDGE_DB` (`audio.py`), the Speech Check bands in `speechcheck.py`, `MIN_PROGRAM_MIB` and `NEEDED_MIB` (`handoff.py`). Read the relevant ADR before changing one, and update it in the same change.

Engine pins are in `config/voice-requirements.txt` and `config/face-requirements.txt`. The tuned face-engine graph is `config/infinitetalk-graph.json`: fp8 weights, the `multitalk` scheduler, merged LoRA, 6 steps and 34 blocks swapped. ADR 0002 names the Q8 GGUF stack it replaced.

### Keeping personal content safe

`persona/` and `platform/` hold a real person's face, voice and Scripts. Do not commit, upload or copy them out of the repo. Tests build their own layout in a temporary folder and never touch them. They are not in git, so back them up yourself.

## 6. Checking the code

```sh
uv run mypy                    # strict, over src/ and tests/
uv run pytest -q -n auto       # the whole suite
```

Both run in about 20 s with no GPU, models or network. There is no linter or formatter. A commit hook (enable once per clone with `git config core.hooksPath .githooks`) and the CI workflow in `.github/workflows/check.yml` run the same two commands.

The commands that use the GPU, ask questions, call `sudo` or download up to 38 GB (`voiceover`, `video`, `models --fix` and the install scripts) are not part of the checks; run them yourself.

## 7. Troubleshooting

Errors print as one line starting `clonecraft:` with exit code 1, naming the file or program at fault. For problems with making a Voiceover or Video, see the table in [operator-guide.md](operator-guide.md#7-when-something-goes-wrong). Machine-level problems:

| Symptom | Cause and fix |
|---|---|
| `nvidia-smi was not found` | The NVIDIA driver tools are not on the PATH. Install the driver or fix the PATH. |
| `torch sees no GPU` at the end of the face install | The driver or CUDA is not working. Check `nvidia-smi` first. |
| SageAttention fails to build | The CUDA toolkit is missing or older than 12.8, or `CUDA_HOME` / `TORCH_CUDA_ARCH_LIST` is wrong for your card. |
| `uv` cannot create the 3.14 environment | `uv venv --python 3.14` needs a Python 3.14 that uv can download or find. |
| `models --fix` reports `download from … failed` | The network or the Hugging Face URL failed. Run it again; only missing or wrong files are fetched. |
| `…still fails its check, so it was not kept` | The downloaded file's size or sha256 does not match `config/models.toml`. Check the entry and the URL. |
| `The model list is missing`, `… is not a valid model list` or `… points outside models/` | `config/models.toml` is damaged. Restore it from git. |
| `the voice engine stopped unexpectedly (exit code N)` | The voice worker crashed; its own output is printed above the error. Often not enough GPU memory or a broken environment: re-run `install-voice-engine.sh`. |
| `ComfyUI did not answer within 300 s of starting` | ComfyUI could not start. Read its output above the error, check `vendor/face-env`, and re-run `install-face-engine.sh`. |
| `ComfyUI refused the graph` / `ComfyUI could not render the face` | The graph, a node or a model file is wrong or missing. The message names the node. Run `clonecraft models`, and check `config/infinitetalk-graph.json`. |
| `ComfyUI finished but wrote no face clip` | The graph ran but produced nothing. Check the graph's output node. |
| `google-chrome was not found on PATH` | Install Google Chrome so `google-chrome` runs from a terminal. Only Scripts with Slide cards or a hook need it. |
| The Video step stops with only a little memory free | Another program holds the card. See section 4. |

## 8. What has and has not been verified

This guide was written from the source code, the tests and the repo's records, not by running the install scripts or the render commands again.

- **Measured on the RTX 5070:** a 5-second Video took 437.7 s of face-engine time and 451.4 s for the whole step, within 12 GB (about 8.8 GB reserved at peak). The Voiceover pipeline and the face engine were each run end to end on a short test.
- **Measured on the RTX 5070, 16:9:** an 8-second Video at 832×480 took 560.4 s of face-engine time and peaked at 11,426 MiB of the 12,227 MiB card. The Operator approved it, so 16:9 is on (ADR 0006).
- **Measured on the RTX 5070, full length:** a 77.6-second 9:16 Video took 4,058 s of face-engine time and 4,254 s for the whole step, peaking at 9.09 GB reserved. Over that length the Operator saw unnatural head motion and mouth shapes, and the face drifted (eye make-up and forehead lines changed after about 50 s). The settings are still being tuned.
- **Measured on the RTX 5070, tuned settings (2026-10-26):** with the graph on the fp8 weights and the `multitalk` scheduler (`config/infinitetalk-graph.json`), a 5-second 9:16 face render took 301.9 s (against 370.0 s engine-only before tuning) and an 8-second 16:9 face render took 431.6 s, peaking at 10,735 MiB (against 560.4 s at 11,426 MiB). The same sweep added a per-job watchdog to the face engine. The Operator has not yet compared the tuned and untuned renders side by side.
- **Checked on this machine, cards only:** a 6-second 1080×1920 Video of three Slide cards, drawn by the real headless Chrome from `config/brand-pack-starter`, took 4.9 s with made-up word timings. Each kind of card from the starter pack was also drawn at 1920×1080 by the real Chrome, and its text fit; its 9:16 cards came out unchanged, pixel for pixel. The Operator has not yet looked at a 16:9 card set. No Video with Slide cards or Face sections has been made from a real Voiceover or the real face engine yet; the Face section slicing and kept clips are checked only by the test suite.
- **Not tested:** any hardware or operating system other than the one above.
