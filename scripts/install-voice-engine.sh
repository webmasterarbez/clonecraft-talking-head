#!/bin/sh
# Install the voice engine (VoxCPM2 and faster-whisper) into vendor/voice-env (git-ignored)
# so it matches config/voice-requirements.txt exactly. Run from the repo root:  sh scripts/install-voice-engine.sh
set -eu
ENV=vendor/voice-env
[ -x "$ENV/bin/python" ] || uv venv --python 3.14 "$ENV"
uv pip sync --python "$ENV/bin/python" config/voice-requirements.txt
"$ENV/bin/python" -c "import voxcpm, faster_whisper; print('voice engine imports ok')"
