import re
import pytest

from clonecraft.cli import main
import numpy as np

from tests.support import (
    FakeFaceEngine,
    Project,
    Samples,
    decode_audio,
    ffprobe,
    measure_loudness,
    read_wav,
    silence,
    tone,
    video_stream,
    write_banded_likeness,
    write_wav,
)


def best_correlation(a: Samples, b: Samples) -> float:
    """Highest normalised cross-correlation of two signals over all offsets."""
    x, y = a.astype(np.float64), b.astype(np.float64)
    size = 1 << (len(x) + len(y)).bit_length()
    corr = np.fft.irfft(np.fft.rfft(x, size) * np.conj(np.fft.rfft(y, size)), size)
    return float(np.abs(corr).max() / (np.linalg.norm(x) * np.linalg.norm(y)))


def run_video(project: Project, engine: FakeFaceEngine, script: str = "script-01", aspect: str | None = None) -> int:
    args = ["video", project.channel_ref, script] + (["--format", aspect] if aspect else [])
    return main(args, root=project.root, face_engine=engine)


@pytest.fixture
def ready(project: Project) -> Project:
    write_banded_likeness(project.likeness)
    project.write_voiceover("script-01", seconds=1.0)
    return project


def test_video_is_written_named_after_the_script_in_the_channels_format(ready: Project) -> None:
    assert run_video(ready, FakeFaceEngine()) == 0

    stream = video_stream(ready.video("script-01"))
    assert (stream["width"], stream["height"]) == (1080, 1920)
    assert stream["avg_frame_rate"] == "30/1"


def test_video_is_as_long_as_the_voiceover_and_its_audio_is_the_voiceover(ready: Project) -> None:
    run_video(ready, FakeFaceEngine(extra_seconds=0.5))  # the face clip runs 0.5 s past the audio

    info = ffprobe(ready.video("script-01"))
    assert float(info["format"]["duration"]) == pytest.approx(1.06, abs=0.1)  # 1.0 s of tone + 0.03 s padding each side
    _, original = read_wav(ready.voiceover("script-01"))
    _, heard = decode_audio(ready.video("script-01"))
    # the Video's audio is gained to -14 LUFS and faded out over its last 0.4 s, which the correlation partly sees,
    # so the bar is 0.9: the shape is still the Voiceover's, and the gain is tested on its own
    assert best_correlation(original, heard) > 0.9


def write_voiceover_samples(project: Project, *parts: Samples) -> None:
    """Write the Voiceover as the given pieces, joined: the tone and silence the other tests use, but at chosen levels."""
    write_wav(project.voiceover("script-01"), np.concatenate(parts))


def test_the_videos_audio_is_normalised_to_minus_14_lufs_and_the_approved_voiceover_is_left_as_it_was(
    ready: Project,
) -> None:
    write_voiceover_samples(ready, silence(0.03), tone(3.0, amplitude=0.03), silence(0.03))  # a quiet take
    before = ready.voiceover("script-01").read_bytes()
    # a tone of amplitude 0.03 has RMS 0.03 / sqrt(2) = 0.0212, which is 20 * log10(0.0212) = -33.5 dBFS: about -34 LUFS
    assert measure_loudness(ready.voiceover("script-01"))[0] < -30

    assert run_video(ready, FakeFaceEngine()) == 0

    # the approved look's target is -14 LUFS, within 1.5 LUFS: the Video's audio is about 20 dB louder than the take
    lufs, _ = measure_loudness(ready.video("script-01"))
    assert lufs == pytest.approx(-14.0, abs=1.5)
    assert ready.voiceover("script-01").read_bytes() == before


def test_the_limiter_puts_the_videos_true_peak_at_minus_2_dbfs_after_the_gain(ready: Project) -> None:
    # a quiet take with one 10 ms burst at -0.9 dBFS in the middle, out of the fade-out: the gain of about 20 dB pushes
    # the burst past the QC ceiling
    write_voiceover_samples(
        ready, silence(0.03), tone(1.0, amplitude=0.03), tone(0.01, amplitude=0.9), tone(2.0, amplitude=0.03), silence(0.03)
    )

    assert run_video(ready, FakeFaceEngine()) == 0

    # the limiter is 0.794 linear: 20 * log10(0.794) = -2.0 dBFS. Without it the burst lands at -1.5 dBFS, the
    # loudnorm target. AAC moves a peak a little, so the test allows 0.3 dB: -2.0 +- 0.3 excludes -1.5.
    _, peak = measure_loudness(ready.video("script-01"))
    assert peak == pytest.approx(-2.0, abs=0.3)


def test_a_voiceover_too_short_to_measure_is_left_as_it_is_and_the_video_warns_about_its_loudness(
    ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    write_voiceover_samples(ready, silence(0.03), tone(0.3, amplitude=0.03), silence(0.03))  # a 0.3 s take
    before = ready.voiceover("script-01").read_bytes()

    assert run_video(ready, FakeFaceEngine()) == 0

    # ebur128 measures in 400 ms blocks and reports nothing below its absolute gate, -70 LUFS (EBU R128). A 0.3 s take
    # has no block, so loudnorm finds no loudness, the take passes unchanged, and the Video reads the -70 LUFS floor
    assert "loudness -70.0 LUFS" in capsys.readouterr().err
    assert ready.voiceover("script-01").read_bytes() == before


def test_a_short_loud_take_that_cannot_be_normalised_is_warned_about_for_its_true_peak(
    ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    write_voiceover_samples(ready, silence(0.03), tone(0.3, amplitude=0.9), silence(0.03))  # 0.3 s at -0.9 dBFS

    assert run_video(ready, FakeFaceEngine()) == 0

    # too short to normalise, so the peak stays where the take left it: 20 * log10(0.9) = -0.9 dBFS, over the -1 dBFS ceiling
    assert "true peak" in capsys.readouterr().err


def test_the_videos_audio_fades_out_over_its_last_four_tenths_of_a_second_and_not_before(ready: Project) -> None:
    write_voiceover_samples(ready, silence(0.03), tone(3.0, amplitude=0.03), silence(0.03))  # 0.03 + 3.0 + 0.03 = 3.06 s

    assert run_video(ready, FakeFaceEngine()) == 0

    rate, heard = decode_audio(ready.video("script-01"))
    middle = np.abs(heard[rate : 2 * rate]).max()  # 1.0 s to 2.0 s: well before the fade
    # the fade starts 3.06 - 0.4 = 2.66 s, so 2.0 s to 2.2 s is untouched; the last 10 ms are at 0.01 / 0.4 = 0.025
    # of full level, so they peak at 0.025 of the middle's peak, with room for the AAC encoder
    assert np.abs(heard[2 * rate : round(2.2 * rate)]).max() >= 0.9 * middle
    # a fade of 0.1 s would start at 2.96 s and leave 2.88 s to 2.92 s at full level. The 0.4 s fade is at
    # (3.06 - 2.88) / 0.4 = 0.45 by 2.88 s, so that window peaks at no more than 0.45 of the middle's peak
    assert np.abs(heard[round(2.88 * rate) : round(2.92 * rate)]).max() <= 0.6 * middle
    assert np.abs(heard[-round(0.01 * rate) :]).max() <= 0.1 * middle


def test_a_silent_voiceover_is_written_as_silence_with_a_warning_that_it_cannot_be_normalised(
    ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    write_voiceover_samples(ready, silence(1.0))

    assert run_video(ready, FakeFaceEngine()) == 0

    # the exact wording: the test's own name is in the Video's path, so a bare "silent" would match the path
    assert "the Video's audio is silent in" in capsys.readouterr().err
    assert ready.video("script-01").is_file()


def test_the_face_engine_gets_a_centre_crop_and_the_likeness_file_is_untouched(ready: Project) -> None:
    before = ready.likeness.read_bytes()
    engine = FakeFaceEngine()

    run_video(ready, engine)

    width, height, pixels = engine.portraits[0]
    assert (width, height) == (480, 832)
    assert pixels[:, :, 2].min() > 200  # only the blue middle band: no red or green came in from the sides
    assert pixels[:, :, 0].max() < 60 and pixels[:, :, 1].max() < 60
    assert ready.likeness.read_bytes() == before


def test_remaking_a_video_replaces_the_old_one(ready: Project) -> None:
    run_video(ready, FakeFaceEngine())
    ready.write_voiceover("script-01", seconds=2.0)

    run_video(ready, FakeFaceEngine())

    assert float(ffprobe(ready.video("script-01"))["format"]["duration"]) == pytest.approx(2.06, abs=0.1)
    assert [p.name for p in ready.video("script-01").parent.glob("*.mp4")] == ["script-01.1080x1920.mp4"]


def test_a_script_without_a_voiceover_is_named_in_the_error(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    write_banded_likeness(project.likeness)

    assert run_video(project, FakeFaceEngine()) != 0

    err = capsys.readouterr().err
    assert "script-01" in err and "Voiceover" in err


def test_a_persona_without_a_likeness_is_named_in_the_error(project: Project, capsys: pytest.CaptureFixture[str]) -> None:
    project.write_voiceover("script-01", seconds=1.0)

    assert run_video(project, FakeFaceEngine()) != 0

    err = capsys.readouterr().err
    assert "examplepersona" in err and "Likeness" in err


def test_a_channel_without_a_format_is_named_in_the_error(ready: Project, capsys: pytest.CaptureFixture[str]) -> None:
    (ready.channel_dir / "channel.yaml").write_text("persona: examplepersona\n")

    assert run_video(ready, FakeFaceEngine()) != 0

    err = capsys.readouterr().err
    assert "channel.yaml" in err and "format" in err


def test_without_an_installed_face_engine_the_command_says_so(ready: Project, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["video", ready.channel_ref, "script-01"], root=ready.root) != 0

    assert "face engine" in capsys.readouterr().err


def test_a_face_clip_shorter_than_the_voiceover_is_an_error_and_keeps_the_old_video(
    ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    run_video(ready, FakeFaceEngine())
    before = ready.video("script-01").read_bytes()
    ready.write_voiceover("script-01", seconds=2.0)

    assert run_video(ready, FakeFaceEngine(extra_seconds=-0.5)) != 0

    assert "shorter than its slice of the Voiceover" in capsys.readouterr().err
    assert ready.video("script-01").read_bytes() == before


def test_a_format_that_is_not_nine_by_sixteen_or_sixteen_by_nine_is_not_supported_yet(
    ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    (ready.channel_dir / "channel.yaml").write_text(
        'persona: examplepersona\nformats:\n  - aspect: "4:5"\n    resolution: 1080x1350\n    fps: 30\n'
    )

    assert run_video(ready, FakeFaceEngine()) != 0

    err = capsys.readouterr().err
    assert "4:5" in err and "9:16" in err and "16:9" in err


def test_how_long_the_face_engine_and_the_whole_video_step_took_is_reported(
    ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_video(ready, FakeFaceEngine(takes_seconds=0.5)) == 0

    out = capsys.readouterr().out
    timed = re.search(r"face engine (\d+\.\d) s, whole Video step (\d+\.\d) s", out)
    assert timed, out
    face, whole = float(timed[1]), float(timed[2])
    assert 0.5 <= face < whole  # the render's 0.5 s, inside a step that also crops, upscales and encodes


def test_an_old_single_format_block_is_refused_with_the_fix_named(
    ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    ready.channel_yaml.write_text('persona: examplepersona\nformat:\n  aspect: "9:16"\n  resolution: 1080x1920\n  fps: 30\n')

    assert run_video(ready, FakeFaceEngine()) != 0

    err = capsys.readouterr().err
    assert "channel.yaml" in err and "formats:" in err
    assert not ready.video("script-01").exists()


TWO_FORMATS = (
    'persona: examplepersona\nformats:\n'
    '  - aspect: "9:16"\n    resolution: 1080x1920\n    fps: 30\n'
    '  - aspect: "16:9"\n    resolution: 1920x1080\n    fps: 30\n'
)


def test_a_channel_with_two_formats_needs_format_and_lists_them_when_it_is_left_out(
    ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    ready.channel_yaml.write_text(TWO_FORMATS)

    assert run_video(ready, FakeFaceEngine()) != 0

    err = capsys.readouterr().err
    assert "--format" in err and "9:16" in err and "16:9" in err
    assert not ready.video("script-01").exists()


def test_the_video_is_named_after_the_script_and_its_resolution(ready: Project) -> None:
    assert run_video(ready, FakeFaceEngine()) == 0

    assert ready.video("script-01", "1080x1920").is_file()
    assert not ready.channel_dir.joinpath("videos", "script-01.mp4").exists()


def test_sixteen_by_nine_is_refused_while_its_render_is_not_verified(
    ready: Project, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("clonecraft.cli.SIXTEEN_BY_NINE_VERIFIED", False)
    ready.channel_yaml.write_text(
        'persona: examplepersona\nformats:\n  - aspect: "16:9"\n    resolution: 1920x1080\n    fps: 30\n'
    )

    assert run_video(ready, FakeFaceEngine()) != 0

    err = capsys.readouterr().err
    assert "16:9" in err and "not been verified" in err
    assert not ready.video("script-01", "1920x1080").exists()


def test_a_sixteen_by_nine_video_is_cropped_from_the_horizontal_likeness_at_the_engines_landscape_size(
    ready: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("clonecraft.cli.SIXTEEN_BY_NINE_VERIFIED", True)
    ready.channel_yaml.write_text(TWO_FORMATS)
    write_banded_likeness(ready.likeness_horizontal, width=1600, height=900)
    engine = FakeFaceEngine()

    assert run_video(ready, engine, aspect="16:9") == 0

    width, height, _ = engine.portraits[0]
    assert (width, height) == (832, 480)
    stream = video_stream(ready.video("script-01", "1920x1080"))
    assert (stream["width"], stream["height"]) == (1920, 1080)


def test_a_sixteen_by_nine_video_without_a_horizontal_likeness_names_the_file_it_needs(
    ready: Project, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("clonecraft.cli.SIXTEEN_BY_NINE_VERIFIED", True)
    ready.channel_yaml.write_text(TWO_FORMATS)

    assert run_video(ready, FakeFaceEngine(), aspect="16:9") != 0

    assert "likeness-horizontal" in capsys.readouterr().err
    assert not ready.video("script-01", "1920x1080").exists()


def test_format_names_an_aspect_the_channel_does_not_list_and_nothing_is_made(
    ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    ready.channel_yaml.write_text(TWO_FORMATS)

    assert run_video(ready, FakeFaceEngine(), aspect="4:5") != 0

    err = capsys.readouterr().err
    assert "4:5" in err and "9:16" in err and "16:9" in err
    assert list((ready.channel_dir / "videos").glob("*.mp4")) == []


def test_remaking_one_format_leaves_the_other_formats_video_as_it_was(
    ready: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("clonecraft.cli.SIXTEEN_BY_NINE_VERIFIED", True)
    ready.channel_yaml.write_text(TWO_FORMATS)
    write_banded_likeness(ready.likeness_horizontal, width=1600, height=900)
    assert run_video(ready, FakeFaceEngine(), aspect="16:9") == 0
    landscape = ready.video("script-01", "1920x1080").read_bytes()

    assert run_video(ready, FakeFaceEngine(extra_seconds=1.0), aspect="9:16") == 0

    assert ready.video("script-01", "1920x1080").read_bytes() == landscape
    assert ready.video("script-01", "1080x1920").is_file()


def test_two_formats_with_the_same_aspect_are_refused_and_nothing_is_made(
    ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    ready.channel_yaml.write_text(
        'persona: examplepersona\nformats:\n  - aspect: "9:16"\n    resolution: 1080x1920\n    fps: 30\n'
        '  - aspect: "9:16"\n    resolution: 720x1280\n    fps: 30\n'
    )

    assert run_video(ready, FakeFaceEngine()) != 0

    err = capsys.readouterr().err
    assert "9:16" in err and "channel.yaml" in err
    assert list((ready.channel_dir / "videos").glob("*.mp4")) == []


def test_a_nine_by_sixteen_video_uses_the_vertical_likeness_even_when_a_horizontal_one_exists(ready: Project) -> None:
    ready.channel_yaml.write_text(TWO_FORMATS)
    write_banded_likeness(ready.likeness_horizontal, width=1600, height=900)
    engine = FakeFaceEngine()

    assert run_video(ready, engine, aspect="9:16") == 0

    width, height, pixels = engine.portraits[0]
    assert (width, height) == (480, 832)
    assert pixels[:, :, 2].min() > 200  # the vertical Likeness's blue middle band, not the horizontal one


def test_a_video_is_refused_when_the_script_words_changed_after_its_voiceover(
    ready: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    ready.write_script("script-01", "Hello there.\n")
    ready.script_file("script-01").write_text("Hello there, friend.\n")  # the words change; the Voiceover does not

    assert run_video(ready, FakeFaceEngine()) != 0

    err = capsys.readouterr().err
    assert "not made from the current words" in err and "clonecraft voiceover youtube/@examplechannel script-01" in err


def test_a_change_only_to_delivery_cues_keeps_the_voiceover_current(ready: Project, capsys: pytest.CaptureFixture[str]) -> None:
    ready.write_script("script-01", "Hello there.\n")
    ready.script_file("script-01").write_text("[warmly] Hello there.\n")  # a cue is not a change to the words

    assert run_video(ready, FakeFaceEngine()) == 0
    assert "not made from the current words" not in capsys.readouterr().err
