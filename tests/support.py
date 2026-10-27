"""Test helpers: a temporary project layout, a fake voice engine, and WAV readers."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from clonecraft.gpu import GpuError, GpuProgram
from clonecraft.voice import Heard, Word

RATE = 48_000
Samples = npt.NDArray[np.int16]


def read_wav(path: Path) -> tuple[int, Samples]:
    with wave.open(str(path), "rb") as f:
        assert f.getnchannels() == 1 and f.getsampwidth() == 2
        data = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16)
        return f.getframerate(), data


def write_wav(path: Path, samples: Samples, rate: int = RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(samples.astype(np.int16).tobytes())


def longest_quiet_run_seconds(samples: Samples, rate: int, below_db: float = -45.0) -> float:
    """Longest stretch whose samples all sit below `below_db` full scale, in seconds."""
    quiet = np.abs(samples.astype(np.float64)) <= 32768 * 10 ** (below_db / 20)
    longest = run = 0
    for q in quiet:
        run = run + 1 if q else 0
        longest = max(longest, run)
    return longest / rate


def tone(seconds: float, amplitude: float = 0.5, hz: float = 220.0, rate: int = RATE) -> Samples:
    """A cosine tone, so it starts at full amplitude: an unfaded start is a click."""
    t = np.arange(int(seconds * rate)) / rate
    return (np.cos(2 * np.pi * hz * t) * amplitude * 32767).astype(np.int16)


def silence(seconds: float, rate: int = RATE) -> Samples:
    return np.zeros(int(seconds * rate), dtype=np.int16)


@dataclass(frozen=True)
class Take:
    """What one call to the fake voice engine gives back, and what the fake transcriber hears in it."""

    heard: str | None = None  # None hears exactly the text that was asked for
    seconds: float = 1.0  # how long the speech lasts
    babble: float = 0.0  # loud audio the transcriber does not hear, 0.2 s after the speech, like the engine running on
    early: float = 0.0  # the transcriber ends the last word this long before the speech ends, as Whisper does


@dataclass
class FakeVoiceEngine:
    """Stands in for the real voice engine at its boundary.

    Every piece it speaks is a tone with 0.3 s of silence on each side, like a real take's padding,
    and the fake transcriber hears the piece's words spread evenly over the tone. `takes` scripts the
    calls in order; calls past the list get a plain Take(). Options shape what a piece contains so
    tests can probe the assembly.
    """

    inner_pause: float = 0.0
    pause_amplitude: float = 0.0  # the inner pause is a hum this loud instead of silence
    tail: float = 0.0
    rate: int = RATE
    raises: Exception | None = None
    takes: list[Take] = field(default_factory=list)
    calls: list[tuple[str | None, str]] = field(default_factory=list)
    references: list[Path] = field(default_factory=list)
    heard: dict[Path, tuple[str, float, float]] = field(default_factory=dict)
    words_in: dict[Path, list[Word]] = field(default_factory=dict)  # what the transcriber hears in a whole file

    def synthesize(self, text: str, style: str | None, reference: Path, out: Path) -> None:
        if self.raises is not None:
            raise self.raises
        take = self.takes[len(self.calls)] if len(self.calls) < len(self.takes) else Take()
        self.calls.append((style, text))
        self.references.append(reference)
        body = [tone(take.seconds, rate=self.rate)]
        if self.inner_pause:
            body = [tone(0.5, rate=self.rate), self._pause(), tone(0.5, rate=self.rate)]
        if self.tail:
            body.append(tone(self.tail, amplitude=0.03, rate=self.rate))  # about -30 dBFS: still voiced
        pad = silence(0.3, self.rate)
        speech = np.concatenate(body)
        self.heard[out] = (take.heard if take.heard is not None else text, 0.3, 0.3 + len(speech) / self.rate - take.early)
        babble = [silence(0.2, self.rate), tone(take.babble, rate=self.rate)] if take.babble else []
        write_wav(out, np.concatenate([pad, speech, *babble, pad]), self.rate)

    def transcribe(self, audio: Path) -> Heard:
        if audio in self.words_in:
            timed = self.words_in[audio]
            return Heard(" ".join(w.text for w in timed), timed)
        if audio not in self.heard:  # a whole Voiceover: every piece spoken, spread over the file
            rate, samples = read_wav(audio)
            spoken = [text for i, (_, text) in enumerate(self.calls) if i == 0 or self.calls[i - 1][1] != text]
            self.heard[audio] = (" ".join(spoken), 0.0, len(samples) / rate)
        text, start, end = self.heard[audio]
        words = text.split()
        step = (end - start) / max(len(words), 1)
        return Heard(text, [Word(w, start + i * step, start + (i + 1) * step) for i, w in enumerate(words)])

    def _pause(self) -> Samples:
        if self.pause_amplitude:
            return tone(self.inner_pause, amplitude=self.pause_amplitude, rate=self.rate)
        return silence(self.inner_pause, self.rate)


def ffprobe(path: Path) -> dict[str, Any]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
        stdin=subprocess.DEVNULL).stdout
    result: dict[str, Any] = json.loads(out)
    return result


def video_stream(path: Path) -> dict[str, Any]:
    return next(s for s in ffprobe(path)["streams"] if s["codec_type"] == "video")


def decode_image(path: Path) -> tuple[int, int, npt.NDArray[np.uint8]]:
    """Width, height and RGB pixels of an image file, decoded by ffmpeg."""
    info = ffprobe(path)["streams"][0]
    width, height = int(info["width"]), int(info["height"])
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        check=True, capture_output=True,
        stdin=subprocess.DEVNULL).stdout
    return width, height, np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3)


def decode_audio(path: Path) -> tuple[int, Samples]:
    """Mono 16-bit audio of a media file at 48 kHz, decoded by ffmpeg."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
        check=True, capture_output=True,
        stdin=subprocess.DEVNULL).stdout
    return RATE, np.frombuffer(raw, dtype=np.int16)


def measure_loudness(path: Path) -> tuple[float, float]:
    """Integrated loudness in LUFS and true peak in dBFS of a media file, from ffmpeg's EBU R128 summary."""
    err = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True, stdin=subprocess.DEVNULL,
    ).stderr
    summary = err[err.rfind("Summary:") :]
    lufs = re.search(r"I:\s+(-?[\d.]+|-inf)\s+LUFS", summary)
    peak = re.search(r"Peak:\s+(-?[\d.]+|-inf)\s+dBFS", summary)
    assert lufs and peak, f"ffmpeg printed no loudness summary for {path}"
    return float(lufs.group(1)), float(peak.group(1))


def write_banded_likeness(path: Path, width: int = 600, height: int = 800) -> None:
    """A Likeness whose left 75 columns are red, right 75 green and middle blue.

    A 9:16 crop of full height is 450 columns wide, so a centred crop keeps only blue
    (columns 75 to 525 of 600) and any off-centre crop shows red or green.
    """
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :75] = (255, 0, 0)
    image[:, 75:-75] = (0, 0, 255)
    image[:, -75:] = (0, 255, 0)
    ppm = path.with_suffix(".ppm")
    path.parent.mkdir(parents=True, exist_ok=True)
    ppm.write_bytes(f"P6 {width} {height} 255\n".encode() + image.tobytes())
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(ppm), str(path)], check=True, stdin=subprocess.DEVNULL)
    ppm.unlink()


@dataclass
class FakeFaceEngine:
    """Stands in for the real face engine at its boundary.

    Like InfiniteTalk it returns a 480x832, 25 fps clip that runs past the audio, because
    the real engine rounds its length up to whole windows.
    """

    extra_seconds: float = 0.5
    takes_seconds: float = 0.0  # how long a render takes
    raises: BaseException | None = None
    log: list[str] | None = None  # shared with a FakeGpu to show when the render happened
    portraits: list[tuple[int, int, npt.NDArray[np.uint8]]] = field(default_factory=list)
    sessions: int = 0  # how many times render was called
    slices: list[float] = field(default_factory=list)  # how long each audio slice it was given lasts

    def render(self, portrait: Path, jobs: list[tuple[Path, Path]]) -> None:
        if self.log is not None:
            self.log.append("render")
        if self.raises is not None:
            raise self.raises
        self.sessions += 1
        width, height, pixels = decode_image(portrait)
        self.portraits.append((width, height, pixels))
        time.sleep(self.takes_seconds)
        for voiceover, out in jobs:
            rate, audio = read_wav(voiceover)
            self.slices.append(len(audio) / rate)
            seconds = len(audio) / rate + self.extra_seconds
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=gray:s={width}x{height}:r=25:d={seconds}",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", str(out)],
                check=True,
                stdin=subprocess.DEVNULL)


CARD_COLOURS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (0, 255, 255), (255, 0, 255)]


@dataclass
class FakeBrowser:
    """Stands in for headless Chrome at its boundary.

    Draws the n-th card it is asked for as a solid CARD_COLOURS[n], so a test can tell which card shows
    at a moment of the Video. A page holding any text in `overflowing` does not fit its frame.
    """

    overflowing: set[str] = field(default_factory=set)
    pages: list[str] = field(default_factory=list)
    sizes: list[tuple[int, int]] = field(default_factory=list)
    fit_sizes: list[tuple[int, int]] = field(default_factory=list)

    def screenshot(self, page: Path, width: int, height: int, out: Path) -> None:
        colour = CARD_COLOURS[len(self.pages) % len(CARD_COLOURS)]
        self.pages.append(page.read_text())
        self.sizes.append((width, height))
        ppm = out.with_suffix(".ppm")
        ppm.write_bytes(f"P6 {width} {height} 255\n".encode() + bytes(colour) * (width * height))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(ppm), str(out)], check=True, stdin=subprocess.DEVNULL)
        ppm.unlink()

    def fits(self, page: Path, width: int, height: int) -> bool:
        self.fit_sizes.append((width, height))
        return not any(text in page.read_text() for text in self.overflowing)


def frame_colour(video: Path, at: float, down: float = 0.5, across: float = 0.5) -> tuple[int, int, int]:
    """The colour `across` and `down` the Video's frame (the middle by default) at `at` seconds."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{at:.3f}", "-i", str(video), "-frames:v", "1", "-f", "rawvideo",
         "-pix_fmt", "rgb24", "-"],
        check=True, capture_output=True, stdin=subprocess.DEVNULL,
    ).stdout
    width, height = (int(video_stream(video)[k]) for k in ("width", "height"))
    middle = (int(height * down) * width + int(width * across)) * 3
    r, g, b = raw[middle : middle + 3]
    return r, g, b


def write_brand_pack(persona_dir: Path, name: str = "plain", **extra: Any) -> Path:
    """A Brand pack with every file and setting the card step checks, and a template that shows the card's text.

    `extra` adds or replaces top-level settings, such as a wordmark or an end card.
    """
    pack = persona_dir / "brand-packs" / name
    (pack / "fonts").mkdir(parents=True)
    for font in ("Ui.ttf", "Mono.ttf"):
        (pack / "fonts" / font).write_bytes(b"font")
    (pack / "mark.svg").write_text("<svg/>")
    settings = {
        "colors": {"teal": "#2dd4bf"},
        "fonts": {"ui": "Ui.ttf", "mono": "Mono.ttf"},
        "mark": "mark.svg", "disclosure": "An AI clone, with consent",
        **extra,
    }
    (pack / "pack.json").write_text(json.dumps(settings))
    (pack / "slide.html").write_text(
        '<style>@font-face{src:url("__FONT_UI__")}@font-face{src:url("__FONT_MONO__")}</style>'
        "<script>const S = __SLIDE__, P = __PACK__;</script>"
    )
    return pack


@dataclass
class Project:
    root: Path
    persona: str = "examplepersona"
    channel_ref: str = "youtube/@examplechannel"

    @property
    def channel_dir(self) -> Path:
        return self.root / "platform" / "youtube" / "channels" / "@examplechannel"

    @property
    def voice_reference(self) -> Path:
        return self.root / "persona" / self.persona / "voice-reference.wav"

    def write_script(self, name: str, text: str) -> None:
        """Write a Script. A Voiceover already made for it is taken to be made from these words."""
        path = self.channel_dir / "scripts" / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        if self.voiceover(name).is_file():
            self.spoken_record(name).write_text(spoken_fingerprint_of(path) + "\n")

    def voiceover(self, name: str) -> Path:
        return self.channel_dir / "voiceovers" / f"{name}.wav"

    def words(self, name: str) -> Path:
        return self.channel_dir / "voiceovers" / f"{name}.words.json"

    def video(self, name: str, resolution: str = "1080x1920") -> Path:
        return self.channel_dir / "videos" / f"{name}.{resolution}.mp4"

    @property
    def channel_yaml(self) -> Path:
        return self.channel_dir / "channel.yaml"

    @property
    def voice_sample(self) -> Path:
        return self.root / "persona" / self.persona / "voice-sample.wav"

    @property
    def candidates_dir(self) -> Path:
        return self.root / "persona" / self.persona / "voice-reference-candidates"

    @property
    def likeness(self) -> Path:
        return self.root / "persona" / self.persona / "likeness.png"

    @property
    def likeness_horizontal(self) -> Path:
        return self.root / "persona" / self.persona / "likeness-horizontal.png"

    def write_voiceover(self, name: str, seconds: float = 2.0) -> None:
        write_wav(self.voiceover(name), np.concatenate([silence(0.03), tone(seconds), silence(0.03)]))
        self.spoken_record(name).write_text(spoken_fingerprint_of(self.channel_dir / "scripts" / f"{name}.md") + "\n")

    def script_file(self, name: str) -> Path:
        return self.channel_dir / "scripts" / f"{name}.md"

    def spoken_record(self, name: str) -> Path:
        return self.channel_dir / "voiceovers" / f"{name}.spoken.sha256"


def make_project(root: Path) -> Project:
    project = Project(root)
    project.channel_dir.mkdir(parents=True)
    (project.channel_dir / "channel.yaml").write_text(
        'persona: examplepersona\nformats:\n  - aspect: "9:16"\n    resolution: 1080x1920\n    fps: 30\n'
    )
    write_wav(project.voice_reference, tone(1.0))
    project.write_script("script-01", "Hello there. This is the first paragraph.")
    return project


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class ModelStore:
    """A tiny model list in a temporary project, with a local folder standing in for the download site."""

    root: Path
    sources: dict[str, bytes] = field(default_factory=dict)

    @property
    def models_dir(self) -> Path:
        return self.root / "models"

    def add(self, path: str, data: bytes, *, on_disk: bytes | None | bool = True, url: str | None = None) -> None:
        """List a model file. `on_disk` True puts the right bytes in models/, False or None leaves it absent,
        and bytes put those (wrong) bytes there. The file is also served from the local source."""
        source = self.root / "source" / path.replace("..", "up")
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(data)
        self.sources[path] = data
        entry = (
            f'[[model]]\npath = "{path}"\npurpose = "test file"\nsize = {len(data)}\n'
            f'sha256 = "{sha256_hex(data)}"\nurl = "{url or source.as_uri()}"\n\n'
        )
        listing = self.root / "config" / "models.toml"
        listing.parent.mkdir(parents=True, exist_ok=True)
        with listing.open("a") as f:
            f.write(entry)
        if on_disk is True:
            on_disk = data
        if isinstance(on_disk, bytes):
            target = self.models_dir / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(on_disk)


GOOD_AMPLITUDE = 0.3
GOOD_LOUDNESS_DB = 20 * float(np.log10(GOOD_AMPLITUDE / np.sqrt(2)))  # RMS of a cosine, in dBFS: about -13.5


def speechy(seconds: float, amplitude: float = GOOD_AMPLITUDE) -> Samples:
    """A tone with a 0.3 s pause at the end of every 3 s, like the natural gaps in speech."""
    block = np.concatenate([tone(2.7, amplitude), silence(0.3)])
    return np.tile(block, int(np.ceil(seconds / 3.0)))[: int(seconds * RATE)]


def write_sample_with_known_regions(path: Path) -> list[float]:
    """A Voice Sample whose stretches are good or bad in known ways, split by 3 s of silence.

    Seconds 0-24 (room for five overlapping 20 s windows), 73-93 and 119-139 are good. The others
    are not: 27-47 holds a 2 s gap, 50-70 holds ten clipped samples,
    96-116 is 9.5 dB too quiet. Returns the starts a good choice makes: the first window of each good stretch.
    """
    gap = silence(3.0)
    with_a_gap = np.concatenate([speechy(8.0), silence(2.0), speechy(10.0)])
    clipped = speechy(20.0)
    clipped[8 * RATE : 8 * RATE + 4_800 : 480] = 32_767  # ten full-scale samples: clipped, but no louder or less steady
    parts = [
        speechy(24.0), gap, with_a_gap, gap, clipped, gap,
        speechy(20.0), gap, speechy(20.0, amplitude=0.1), gap, speechy(20.0),
    ]
    write_wav(path, np.concatenate(parts))
    return [0.0, 73.0, 119.0]


class Answers:
    """Stands in for the Operator typing at a prompt."""

    def __init__(self, *answers: str) -> None:
        self.left = list(answers)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.left:
            raise AssertionError(f"the Operator was asked again with nothing left to say: {prompt!r}")
        return self.left.pop(0)


def service(unit: str, mib: int) -> GpuProgram:
    return GpuProgram(name=unit.split("@")[0].removesuffix(".service"), used_mib=mib, pids=(100,), service=unit)


def plain_program(name: str, mib: int, pid: int = 200) -> GpuProgram:
    return GpuProgram(name=name, used_mib=mib, pids=(pid,), service=None)


@dataclass
class FakeGpu:
    """Stands in for the GPU and the system's way of stopping programs.

    A 12000 MiB card of which the desktop holds 1200. Stopping a program frees its memory and
    starting a service gives it back. Every stop and start is logged, in order.
    """

    known: list[GpuProgram]
    total_mib: int = 12_000
    desktop_mib: int = 1_200
    cannot_start: set[str] = field(default_factory=set)
    cannot_stop: set[str] = field(default_factory=set)
    events: list[str] = field(default_factory=list)
    running: set[str] = field(init=False)

    def __post_init__(self) -> None:
        self.running = {p.key for p in self.known}

    def programs(self) -> list[GpuProgram]:
        return [p for p in self.known if p.key in self.running]

    def free_mib(self) -> int:
        return self.total_mib - self.desktop_mib - sum(p.used_mib for p in self.programs())

    def stop(self, program: GpuProgram) -> None:
        self.events.append(f"stop {program.key}")
        if program.key in self.cannot_stop:
            raise GpuError(f"systemctl stop {program.key} failed")
        self.running.discard(program.key)

    def start(self, unit: str) -> None:
        self.events.append(f"start {unit}")
        if unit in self.cannot_start:
            raise GpuError(f"systemctl start {unit} failed")
        self.running.add(unit)


def spoken_fingerprint_of(script_file: Path) -> str:
    """The fingerprint of a Script's current words, as the Voiceover command records it."""
    from clonecraft.project import ProjectError
    from clonecraft.script import parts_of, spoken_fingerprint

    if not script_file.is_file():
        return spoken_fingerprint("")
    text = script_file.read_text()
    try:
        return spoken_fingerprint(parts_of(text, script_file).spoken)
    except ProjectError:  # an invalid Script is refused by the command under test, not by this helper
        return spoken_fingerprint(text)
