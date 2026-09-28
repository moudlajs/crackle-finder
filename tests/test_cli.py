import argparse
import json
import subprocess
import sys

import pytest
from conftest import needs_ffmpeg
from synth import speech_like, write_wav

from crackle_finder import cli


@pytest.mark.parametrize(
    ("value", "seconds"),
    [("90", 90), ("0", 0), ("45:00", 2700), ("1:05:30", 3930), ("2.5", 2.5), ("1:00:00.5", 3600.5)],
)
def test_parse_time(value, seconds):
    assert cli.parse_time(value) == seconds


@pytest.mark.parametrize("value", ["", "abc", "1:2:3:4", "-5", "1:75", "1:00:60", "1::00"])
def test_parse_time_rejects(value):
    with pytest.raises(argparse.ArgumentTypeError):
        cli.parse_time(value)


def test_end_before_start_is_an_error(tmp_path, caplog):
    assert cli.main(["x.wav", "--start", "10:00", "--end", "5:00"]) == 2
    assert "--end must be after --start" in caplog.text


def test_missing_file(tmp_path, caplog):
    assert cli.main([str(tmp_path / "nope.mp3")]) == 1
    assert "no such file" in caplog.text


def test_missing_ffmpeg_is_explained(defects_wav, monkeypatch, caplog):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    assert cli.main([str(defects_wav)]) == 1
    assert "ffmpeg is required" in caplog.text


@needs_ffmpeg
def test_undecodable_file(tmp_path, caplog):
    bad = tmp_path / "bad.mp3"
    bad.write_text("not audio")
    assert cli.main([str(bad), "--out", str(tmp_path / "r")]) == 1
    assert "ffmpeg could not decode" in caplog.text


@needs_ffmpeg
def test_end_to_end(defects_wav, defects, tmp_path, capsys):
    out = tmp_path / "report"
    assert cli.main([str(defects_wav), "--out", str(out)]) == 0

    folder = out / "episode_01"
    stdout = capsys.readouterr().out
    assert f"5 event(s) -> {folder}/" in stdout
    assert "showing top 5 by score" in stdout
    # Clipping scores highest, so it is rank 1 in the table and the clips.
    assert stdout.splitlines()[-5].split()[:2] == ["1", "0:00:25"]
    lines = (folder / "timestamps.txt").read_text().splitlines()
    assert lines[0].startswith("0:00:05  ")
    assert any(line.startswith("0:00:25  clipping") for line in lines)
    assert any(line.startswith("0:00:33  dropout") for line in lines)
    assert len((folder / "labels.txt").read_text().splitlines()) == 5
    data = json.loads((folder / "events.json").read_text())
    assert data["params"]["z"] == 6.0
    assert len(data["events"]) == 5
    assert (folder / "overview.png").stat().st_size > 10_000


@needs_ffmpeg
def test_section_times_are_relative_to_original(defects_wav, tmp_path):
    out = tmp_path / "report"
    assert cli.main([str(defects_wav), "--start", "20", "--end", "0:40", "--out", str(out)]) == 0
    data = json.loads((out / "episode_01" / "events.json").read_text())
    starts = [e["start"] for e in data["events"]]
    # Only the clipping (25 s) and dropout (33 s) lie inside 20-40 s.
    assert starts == pytest.approx([25.0, 33.0], abs=0.1)


def test_runs_as_a_module_and_reports_errors_on_stderr(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-m", "crackle_finder", str(tmp_path / "nope.mp3")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert proc.stdout == ""
    assert "no such file" in proc.stderr


def clip_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(out.stdout)


@needs_ffmpeg
def test_clips_of_top_events(defects_wav, tmp_path):
    clips = tmp_path / "r" / "episode_01" / "clips"
    assert cli.main([str(defects_wav), "--out", str(tmp_path / "r")]) == 0
    names = sorted(p.name for p in clips.iterdir())
    assert names[0] == "001_0h00m25s_clipping.mp3"
    assert len(names) == 5
    assert clip_duration(clips / names[0]) == pytest.approx(3.0, abs=0.1)

    # A rerun with a smaller --top leaves no stale clips behind.
    assert cli.main([str(defects_wav), "--out", str(tmp_path / "r"), "--top", "2"]) == 0
    assert len(list(clips.iterdir())) == 2


@needs_ffmpeg
def test_clip_near_file_start_is_clamped(tmp_path):
    x = speech_like(20)
    x[int(0.5 * 44100)] += 0.6
    wav = tmp_path / "early.wav"
    write_wav(wav, x)
    assert cli.main([str(wav), "--out", str(tmp_path / "r")]) == 0
    (clip,) = (tmp_path / "r" / "early" / "clips").iterdir()
    assert clip.name == "001_0h00m00s_crackle.mp3"
    assert clip_duration(clip) == pytest.approx(3.0, abs=0.1)


@needs_ffmpeg
def test_no_clips_no_plot(defects_wav, tmp_path):
    assert (
        cli.main([str(defects_wav), "--out", str(tmp_path / "r"), "--no-clips", "--no-plot"]) == 0
    )
    folder = tmp_path / "r" / "episode_01"
    assert not (folder / "clips").exists()
    assert not (folder / "overview.png").exists()
    assert (folder / "timestamps.txt").exists()


@pytest.mark.parametrize("value", ["0", "-1", "abc"])
def test_top_must_be_positive(value, capsys):
    with pytest.raises(SystemExit):
        cli.main(["x.wav", "--top", value])
    assert "whole number >= 1" in capsys.readouterr().err
