"""URL input. A fake yt-dlp on PATH stands in for the real one: no network, ever."""

import json
import os
import stat
import sys

import pytest
from conftest import needs_ffmpeg

from crackle_finder import CrackleFinderError, cli, download

URL = "https://example.com/episode/7"
TITLE = "Episode 7: Crackles & Pops"

FAKE_YTDLP = f"""#!{sys.executable}
import json, os, shutil, sys
args = sys.argv[1:]
with open(os.environ["FAKE_YTDLP_LOG"], "a") as f:
    f.write(json.dumps(args) + "\\n")
if os.environ.get("FAKE_YTDLP_FAIL"):
    print("ERROR: Unsupported URL", file=sys.stderr)
    sys.exit(1)
out = args[args.index("--output") + 1].replace("%(ext)s", "wav")
shutil.copy(os.environ["FAKE_YTDLP_SOURCE"], out)
print(os.environ["FAKE_YTDLP_TITLE"])
"""


@pytest.fixture
def fake_ytdlp(tmp_path, monkeypatch, defects_wav):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    exe = bin_dir / "yt-dlp"
    exe.write_text(FAKE_YTDLP)
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "ytdlp.log"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_YTDLP_LOG", str(log))
    monkeypatch.setenv("FAKE_YTDLP_SOURCE", str(defects_wav))
    monkeypatch.setenv("FAKE_YTDLP_TITLE", TITLE)

    def calls():
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    return calls


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://example.com/a", True),
        ("http://example.com/a", True),
        ("episode.mp3", False),
        ("/tmp/https:/x.mp3", False),
        ("www.example.com/a", False),
    ],
)
def test_is_url(value, expected):
    assert download.is_url(value) is expected


def test_fetch_downloads_single_item_audio(fake_ytdlp):
    path, title = download.fetch(URL)
    assert title == TITLE
    assert path.name == "audio.wav"
    assert path.is_relative_to(download.cache_dir())
    (args,) = fake_ytdlp()
    assert "--no-playlist" in args
    # The URL comes after "--", so it can never be read as an option.
    assert args[-2:] == ["--", URL]


def test_fetch_reuses_the_cache(fake_ytdlp):
    first = download.fetch(URL)
    assert download.fetch(URL) == first
    assert len(fake_ytdlp()) == 1


def test_different_urls_are_cached_separately(fake_ytdlp):
    a, _ = download.fetch(URL)
    b, _ = download.fetch(URL + "?t=1")
    assert a.parent != b.parent
    assert len(fake_ytdlp()) == 2


def test_partial_download_is_not_a_cache_hit(fake_ytdlp):
    folder = download.cache_dir() / "x"
    folder.mkdir(parents=True)
    (folder / "audio.webm.part").write_text("")
    (folder / "audio.webm.ytdl").write_text("")
    assert download._cached_audio(folder) is None


def test_failure_is_reported_and_retried(fake_ytdlp, monkeypatch):
    monkeypatch.setenv("FAKE_YTDLP_FAIL", "1")
    with pytest.raises(CrackleFinderError, match="Unsupported URL"):
        download.fetch(URL)
    monkeypatch.delenv("FAKE_YTDLP_FAIL")
    assert download.fetch(URL)[1] == TITLE
    assert len(fake_ytdlp()) == 2


def test_missing_ytdlp_is_explained(monkeypatch):
    monkeypatch.setattr(download.shutil, "which", lambda _name: None)
    with pytest.raises(CrackleFinderError, match="yt-dlp is required"):
        download.fetch(URL)


def test_cache_follows_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    assert download.cache_dir() == tmp_path / "xdg" / "crackle-finder" / "downloads"


@needs_ffmpeg
def test_cli_with_url_names_report_after_title(fake_ytdlp, tmp_path, capsys):
    out = tmp_path / "report"
    assert cli.main([URL, "--out", str(out), "--no-clips", "--no-plot"]) == 0
    data = json.loads((out / "Episode_7_Crackles_Pops" / "events.json").read_text())
    assert len(data["events"]) == 5
    assert f"{TITLE}: 5 event(s)" in capsys.readouterr().out


def test_cli_without_ytdlp_fails_cleanly(monkeypatch, caplog):
    monkeypatch.setattr(download.shutil, "which", lambda _name: None)
    assert cli.main([URL]) == 1
    assert "yt-dlp is required" in caplog.text
