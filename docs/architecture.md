# Architecture

How the code and the on-disk layout fit together. The commands, checks and gotchas are in `CLAUDE.md`.

- **Entry point.** `src/clonecraft/cli.py`: `main(argv, root=, voice_engine=,
  face_engine=, gpu=, browser=, ask=)` does all the work; `run()` wires in the real
  `SystemGpu` and `VoxCpmEngine`. Tests call `main` with fakes (see
  `CODING_STANDARDS.md`); helpers and a temporary project layout live in
  `tests/support.py`. `run()` wires in the real `InfiniteTalkEngine` (`infinitetalk.py`: ComfyUI started per render and driven over HTTP, graph in `config/infinitetalk-graph.json`, installed by `scripts/install-face-engine.sh`); the `video`
  command needs that install.
- **Slide cards** (ADR 0007). `script.parts_of` splits a Script file into front
  matter, spoken text and the cards after `<!-- slides -->` (`cards.parse`,
  `cards.check_order`). `voiceover` saves the finished Voiceover's word timings
  (`timings.py`, `voiceovers/<name>.words.json`). In `cli._video`,
  `brandpack.choose` picks and checks the Persona's Brand pack, `cards.place`
  turns the slides list and the words into a timeline of Face sections and
  cards, the `Browser` boundary (`browser.py`, real `ChromeBrowser`,
  `FakeBrowser` in tests) draws each card from the pack's `slide.html`,
  `video.faces_for` slices the Voiceover per Face section and finds kept clips
  (`videos/face-sections/`), `video.render_faces` renders only the missing
  ones in one `FaceEngine.render` call inside the GPU handoff, and
  `video.assemble` joins everything, laying the Script's hook
  (`BrandPack.hook_page`, front matter `hook` and `hook_hold`) over the
  opening Face section, the badge (`BrandPack.badge_page`, pack `wordmark`)
  over every Face section, the disclosure pill (`BrandPack.pill_page`) over
  the last Slide card, and the end card (`BrandPack.end_page`, pack
  `end_card`) for `video.END_CARD_S` of silence after the Voiceover. `loudness.py` normalises the Voiceover's audio to
  The approved look's -14 LUFS for the Video and checks the finished Video (ADR 0007). The approved look's frame and hook position live only in `frame.py`. A Script with no slides list is one Face
  section over the whole Voiceover.
- **Errors.** Problems the Operator can fix are raised as `ProjectError`,
  `VoiceEngineError`, `FaceEngineError` or `GpuError`. `main` catches them and
  prints a single line `clonecraft: …` to stderr, then exits with code 1.
- **On-disk layout** (`project.py`, all git-ignored personal content):
  `platform/<platform>/channels/@<handle>/` holds `channel.yaml` (persona and
  a `formats:` list), plus `scripts/<name>.md`, `voiceovers/<name>.wav` and
  `videos/<name>.<width>x<height>.mp4`, one per Format. `persona/<name>/` holds
  `likeness.*` (9:16), optionally `likeness-horizontal.*` (16:9),
  `voice-sample.*`, `voice-reference.wav` and optionally
  `voice-reference.txt` (its transcript). `voicesample.py` proposes three
  reference candidates and asks the Operator to choose one.
- **Voiceover path.** `script.pieces_of` splits a Script into pieces (Delivery
  Cues become `style`, sentences are packed up to `CHUNK_WORDS`). Each piece
  goes through `speechcheck.speak`, which calls `VoiceEngine.synthesize` and
  `VoiceEngine.transcribe` and retries bad takes (ADR 0005), and
  `audio.assemble` joins the kept takes with `JOIN_PAUSE_S`.
- **Voice engine.** VoxCPM2 runs in its own venv (`vendor/voice-env`).
  `voxcpm.py` starts `scripts/voxcpm_worker.py` in that venv once and talks to
  it with one JSON line per request and reply over stdin/stdout. The worker
  must not import the main package. When a transcript exists, no style is
  sent, so Delivery Cues have no audible effect (ADR 0004, which supersedes
  part of ADR 0002).
- **Video path.** `handoff.cleared_gpu` lists programs holding at least
  100 MiB of VRAM and asks the Operator which to stop. It saves the answers in
  `settings.local.yaml` and restarts services afterwards, even on failure
  (ADR 0003). `video.render_faces` crops the Likeness for the chosen Format to
  the engine's size for its aspect (`FACE_SIZES` in `face.py`: 480×832 for 9:16,
  832×480 for 16:9) at 25 fps and upscales the result to the Format. 16:9 is
  on by `SIXTEEN_BY_NINE_VERIFIED` in `cli.py`, set after the Operator approved
  the 832×480 test render (ADR 0006).
- **Models.** About 38 GB of weights live in `models/` (git-ignored). Every
  file is listed with its size, sha256 and URL in `config/models.toml`.
  Engine pins are in `config/voice-requirements.txt` and `config/face-requirements.txt`.

Tuning constants (`CHUNK_WORDS`, `JOIN_PAUSE_S`, `PAUSE_DB`, the Speech Check
bands in `speechcheck.py`, `MIN_PROGRAM_MIB`, `NEEDED_MIB`) were copied from the
earlier project's approved pipeline or measured on this machine's 12 GB RTX 5070. Their reasons are in the ADRs. Read the relevant ADR
before changing one, and update it in the same change.
