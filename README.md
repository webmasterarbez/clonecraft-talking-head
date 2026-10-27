# CloneCraft

CloneCraft turns a finished Script into a talking-head Video of a Persona. It runs entirely on your own machine: the voice and the face are made by local engines and model files kept inside this repo, and no Likeness, voice or Script is sent to a hosted service (ADR 0001). Writing Scripts and publishing Videos are outside its scope.

It is made for one person, the Operator, who sets it up and runs it.

## How it works

```
Script ──► Voiceover ──► Video
  (you     clonecraft      clonecraft
  write)   voiceover       video
```

1. You write a **Script** and put it in a **Channel**'s folder.
2. `clonecraft voiceover` speaks it in the **Persona**'s cloned voice and checks each piece against the Script's words. You listen to the **Voiceover** and approve it.
3. `clonecraft video` animates the Persona's **Likeness** to speak the Voiceover, as one continuous shot, and writes the **Video**. A Script with a list of **Slide cards** mixes cards in a **Brand pack**'s look with **Face sections**, and only the Face sections are rendered on the GPU.

The terms in bold are defined in [GLOSSARY.md](GLOSSARY.md) and used the same way everywhere in these docs.

## What you need

- Linux with an NVIDIA GPU of at least 12 GB. It is built and tested on an RTX 5070 (12 GB). macOS, Windows and AMD GPUs are not supported.
- About 38 GB of disk for model files, plus room for the two engine installs.
- `uv`, `git`, `ffmpeg` (with `ffprobe`) and `nvidia-smi` on the PATH, and Google Chrome for Slide cards and the hook.
- A Likeness (one still portrait) and a Voice Sample (a long recording of the real voice) for each Persona.

## Quickstart

Run everything from the repo root.

```sh
uv sync                                      # the main environment
sh scripts/install-voice-engine.sh           # voice engine into vendor/voice-env
sh scripts/install-face-engine.sh            # face engine into vendor/face-env (needs the CUDA toolkit)
uv run clonecraft models --fix               # download and check the ~38 GB of model files

uv run clonecraft voiceover youtube/@examplechannel script-01
uv run clonecraft video youtube/@examplechannel script-01
```

## Read next

| If you want to | Read |
|---|---|
| Make a Voiceover and a Video, step by step | [docs/operator-guide.md](docs/operator-guide.md) |
| Install, check, update or fix the machine | [docs/setup-and-maintenance.md](docs/setup-and-maintenance.md) |
| Know what a word means | [GLOSSARY.md](GLOSSARY.md) |
| Know why it works the way it does | [docs/adr/](docs/adr/) |

## Working on the code

`mypy` (strict) and `pytest` are the whole check; run both with `uv run mypy` and `uv run pytest -q -n auto`. Enable the commit hook once per clone with `git config core.hooksPath .githooks`. The architecture notes are in [CLAUDE.md](CLAUDE.md) and the review rules in [CODING_STANDARDS.md](CODING_STANDARDS.md).

## Your personal content stays out of git

`persona/` (Likenesses and voices) and `platform/` (Channels, Scripts, Voiceovers and Videos) hold a real person's face, voice and words. Both are git-ignored and must never be committed or uploaded. Back them up yourself.

Your Persona and Channel folders are created by you, on your machine, and are never part of the repository. The layout is in [docs/operator-guide.md](docs/operator-guide.md#1-lay-out-your-files); the examples there use made-up names only.

## License

CloneCraft is released under the MIT License (see [LICENSE](LICENSE)). The fonts in `config/brand-pack-starter/fonts/` are licensed under the SIL Open Font License (see the `OFL-*.txt` files beside them). The model files in `models/` are downloaded from the sources listed in `config/models.toml`, each under its own licence; check it before you publish a Video made with them. The Claude Code skills in `.claude/skills/` that come from Matt Pocock's skills collection are MIT-licensed (see `.claude/skills/LICENSE.mattpocock-skills`).
