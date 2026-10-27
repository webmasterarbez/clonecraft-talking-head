# VoxCPM2 for the voice, InfiniteTalk in ComfyUI for the face

The Voice Clone and Voiceover come from VoxCPM2. The Video comes from InfiniteTalk (Wan2.1 image-to-video 14B, Q8 GGUF, with the Lightx2v 6-step LoRA), run through ComfyUI and ComfyUI-WanVideoWrapper. Each runs in its own environment inside this repo, at the pinned versions in `config/voice-requirements.txt` and `config/face-requirements.txt`. This is the only stack whose output has been approved on this machine's 12 GB RTX 5070. Its code and weights licences allow commercial use. VoxCPM2 takes a free-text style instruction, which is how Delivery Cues reach the voice.

VoxCPM2 runs in its "controllable cloning" mode: the reference audio alone, with no transcript. Its "ultimate cloning" mode (reference plus exact transcript) copies the voice more closely, but it ignores style instructions, so Delivery Cues would stop working. Don't add a transcript to "improve" the clone without reopening this decision. The earlier approved voices used ultimate cloning, so controllable cloning is unproven on this machine until the first Voiceover is heard.

## Considered Options

- **Voice:** IndexTTS-2.5 has a revocable custom licence. Chatterbox-Turbo has a closed list of cue tags, a 40 s limit per call, and a pinned torch that doesn't support Blackwell. Fish S2-Pro needs ≥24 GB of VRAM.
- **Face:** these were tried here and rejected: LTX-2.3 IA2V (joins snap back), LatentSync (jerky), EchoMimic v3 and SeedVR2. MuseTalk, Wav2Lip and SadTalker are weaker. StableAvatar and LongCat-Video-Avatar are untested here. Wan2GP isn't needed, because ComfyUI's torch 2.14 cu130 build runs on Blackwell.

## Consequences

Rendering takes about 10 GB of VRAM. The output is 480×832 at 25 fps, so every Video is upscaled to the Channel's Format. A continuous talking head longer than about 27 s hasn't been rendered here yet, and InfiniteTalk warns of colour shift past about a minute.

The choice of cloning mode is superseded by `0004-clone-from-the-reference-with-its-transcript.md`.

The 16:9 size (832×480) and its Likeness are decided in `0006-a-likeness-per-orientation-and-formats-named-by-aspect.md`.
