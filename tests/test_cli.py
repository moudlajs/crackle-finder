import argparse
import json
import subprocess
import sys

import pytest
from conftest import needs_ffmpeg

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
    assert f"5 event(s) -> {folder}/" in capsys.readouterr().out
    lines = (folder / "timestamps.txt").read_text().splitlines()
    assert lines[0].startswith("0:00:05  ")
    assert any(line.startswith("0:00:25  clipping") for line in lines)
    assert any(line.startswith("0:00:33  dropout") for line in lines)
    assert len((folder / "labels.txt").read_text().splitlines()) == 5
    data = json.loads((folder / "events.json").read_text())
    assert data["params"]["z"] == 6.0
    assert len(data["events"]) == 5


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
