#!/bin/sh
# Install the face engine (InfiniteTalk in ComfyUI) into vendor/ (git-ignored): ComfyUI and its two node packs at
# the pinned commits with CloneCraft's patches, and vendor/face-env matching config/face-requirements.txt exactly.
# SageAttention is compiled once into vendor/wheels, which needs the CUDA toolkit (12.8 or later) in $CUDA_HOME.
# Run from the repo root:  sh scripts/install-face-engine.sh
set -eu
COMFY=vendor/ComfyUI
NODES=$COMFY/custom_nodes
ENV=vendor/face-env
WHEELS=vendor/wheels
export CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"
export TORCH_CUDA_ARCH_LIST="${TORCH_CUDA_ARCH_LIST:-12.0}"  # the RTX 5070

pinned() {  # folder, repo, commit
    [ -d "$1/.git" ] || git clone --quiet "$2" "$1"
    git -C "$1" cat-file -e "$3^{commit}" 2>/dev/null || git -C "$1" fetch --quiet origin
    git -C "$1" checkout --quiet --force "$3"
}
pinned $COMFY https://github.com/comfyanonymous/ComfyUI.git 29e28e2b488e7739c351c331d73da25aa435da5c
pinned $NODES/ComfyUI-WanVideoWrapper https://github.com/kijai/ComfyUI-WanVideoWrapper.git 088128b224242e110d3906c6750e9a3a348a659b
pinned $NODES/ComfyUI-VideoHelperSuite https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git 4d907bee61e92c2e65af3bd6383a4e4d356126d1
pinned vendor/SageAttention https://github.com/thu-ml/SageAttention.git d1a57a546c3d395b1ffcbeecc66d81db76f3b4b5
git -C $NODES/ComfyUI-WanVideoWrapper apply "$PWD/config/face-wav2vec2.patch"  # transformers 5.x lost per-layer states
git -C vendor/SageAttention apply "$PWD/config/sageattention-cxx20.patch"  # torch 2.14 headers need C++20

[ -x "$ENV/bin/python" ] || uv venv --python 3.12 "$ENV"
mkdir -p $WHEELS
SYNC="uv pip sync --python $ENV/bin/python --index-strategy unsafe-best-match --find-links $WHEELS"
if ! ls $WHEELS/sageattention-2.2.0-*.whl >/dev/null 2>&1; then
    grep -v '^sageattention' config/face-requirements.txt > "$ENV/without-sageattention.txt"
    $SYNC "$ENV/without-sageattention.txt"
    uv build --wheel --no-build-isolation --python "$ENV/bin/python" --out-dir $WHEELS vendor/SageAttention
fi
$SYNC config/face-requirements.txt
"$ENV/bin/python" -c "import torch, sageattention; assert torch.cuda.is_available(), 'torch sees no GPU'; print('face engine imports ok')"
