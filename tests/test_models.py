import os
from pathlib import Path

import pytest

from clonecraft.cli import main
from tests.support import ModelStore


@pytest.fixture
def store(tmp_path: Path) -> ModelStore:
    return ModelStore(tmp_path)


def run_models(store: ModelStore, *flags: str) -> int:
    return main(["models", *flags], root=store.root)


def test_a_folder_with_every_listed_file_intact_reports_all_good(
    store: ModelStore, capsys: pytest.CaptureFixture[str]
) -> None:
    store.add("voice/model.bin", b"voice weights")
    store.add("face/model.bin", b"face weights")

    assert run_models(store) == 0

    out = capsys.readouterr().out
    assert "OK voice/model.bin" in out and "OK face/model.bin" in out
    assert "all 2 model files are good" in out


def test_a_missing_a_truncated_and_a_wrong_file_are_each_reported_by_name(
    store: ModelStore, capsys: pytest.CaptureFixture[str]
) -> None:
    store.add("a/missing.bin", b"never copied", on_disk=False)
    store.add("b/truncated.bin", b"the whole file", on_disk=b"the whole")
    store.add("c/wrong.bin", b"right content", on_disk=b"wrong bytes!!")  # same 13 bytes, different content
    store.add("d/fine.bin", b"fine")

    assert run_models(store) == 1

    out = capsys.readouterr().out
    assert "MISSING a/missing.bin" in out
    assert "WRONG SIZE (9 bytes, expected 14) b/truncated.bin" in out
    assert "WRONG CONTENT c/wrong.bin" in out
    assert "OK d/fine.bin" in out
    assert "3 of 4 model files need attention" in out


def test_a_missing_model_list_is_named_in_the_error(store: ModelStore, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_models(store) == 1

    assert "models.toml" in capsys.readouterr().err


def test_fix_replaces_only_the_missing_and_wrong_files_then_rechecks(
    store: ModelStore, capsys: pytest.CaptureFixture[str]
) -> None:
    store.add("a/missing.bin", b"never copied", on_disk=False)
    store.add("b/wrong.bin", b"right content", on_disk=b"wrong bytes!!")
    store.add("c/fine.bin", b"fine")
    untouched = store.models_dir / "c" / "fine.bin"
    os.utime(untouched, (1_000_000_000, 1_000_000_000))

    assert run_models(store, "--fix") == 0

    out = capsys.readouterr().out
    assert "FIXED a/missing.bin" in out and "FIXED b/wrong.bin" in out and "FIXED c/fine.bin" not in out
    assert "all 3 model files are good" in out
    assert (store.models_dir / "a" / "missing.bin").read_bytes() == b"never copied"
    assert (store.models_dir / "b" / "wrong.bin").read_bytes() == b"right content"
    assert untouched.stat().st_mtime == 1_000_000_000
    assert run_models(store) == 0


def test_a_download_that_fails_is_an_error_naming_the_file(store: ModelStore, capsys: pytest.CaptureFixture[str]) -> None:
    store.add("a/gone.bin", b"data", on_disk=False, url=(store.root / "nowhere" / "gone.bin").as_uri())

    assert run_models(store, "--fix") == 1

    err = capsys.readouterr().err
    assert "a/gone.bin" in err and "download" in err
    assert not (store.models_dir / "a" / "gone.bin").exists()


def test_a_download_that_still_fails_its_check_is_an_error_and_is_not_kept(
    store: ModelStore, capsys: pytest.CaptureFixture[str]
) -> None:
    store.add("a/bad.bin", b"expected bytes", on_disk=False)
    (store.root / "source" / "a" / "bad.bin").write_bytes(b"different bytes")  # same length, different content

    assert run_models(store, "--fix") == 1

    err = capsys.readouterr().err
    assert "a/bad.bin" in err and "still fails" in err
    assert sorted(p.name for p in (store.models_dir / "a").iterdir()) == []  # no file and no partial download left


def test_fix_never_touches_anything_outside_models(store: ModelStore, capsys: pytest.CaptureFixture[str]) -> None:
    store.add("../outside.bin", b"escape", on_disk=False)
    stray = store.models_dir / "unlisted.bin"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_bytes(b"not on the list")

    assert run_models(store, "--fix") == 1

    assert "../outside.bin" in capsys.readouterr().err
    assert not (store.root / "outside.bin").exists()
    assert stray.read_bytes() == b"not on the list"


@pytest.mark.parametrize(
    "listing",
    [
        pytest.param('[[model]]\npath = "a.bin"\nsize = 3\nurl = "file:///x"\n', id="entry without a sha256"),
        pytest.param("[[model]\npath = ", id="not valid TOML"),
    ],
)
def test_a_malformed_model_list_is_an_error_naming_the_file(
    store: ModelStore, capsys: pytest.CaptureFixture[str], listing: str
) -> None:
    (store.root / "config").mkdir()
    (store.root / "config" / "models.toml").write_text(listing)

    assert run_models(store) == 1

    err = capsys.readouterr().err
    assert "models.toml" in err and "Traceback" not in err
