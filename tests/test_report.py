import json

import pytest

from crackle_finder.detect import Event
from crackle_finder.report import (
    clip_name,
    format_summary,
    format_table,
    format_timestamp,
    natural_key,
    safe_name,
    write_json,
    write_labels,
    write_timestamps,
)

EVENTS = [
    Event(start=754.35, end=754.5, score=18.4, kind="crackle", hits=2),
    Event(start=5.0, end=5.05, score=24.7, kind="click", hits=1),
]


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "0:00:00"),
        (5.99, "0:00:05"),
        (754.35, "0:12:34"),
        (3930, "1:05:30"),
        (36000, "10:00:00"),
    ],
)
def test_format_timestamp(seconds, expected):
    assert format_timestamp(seconds) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Episode 12: The Return!", "Episode_12_The_Return"),
        ("Príliš žluťoučký kůň", "Prilis_zlutoucky_kun"),
        ("../../etc/passwd", "etc_passwd"),
        ("   ", "untitled"),
        ("日本語", "untitled"),
        ("a" * 200, "a" * 80),
    ],
)
def test_safe_name(name, expected):
    assert safe_name(name) == expected


def test_timestamps_sorted_by_time(tmp_path):
    path = tmp_path / "timestamps.txt"
    write_timestamps(EVENTS, path)
    assert path.read_text() == "0:00:05  click  (score 25)\n0:12:34  crackle  (score 18)\n"


def test_audacity_labels(tmp_path):
    path = tmp_path / "labels.txt"
    write_labels(EVENTS, path)
    assert path.read_text() == "5.000\t5.050\tclick (25)\n754.350\t754.500\tcrackle (18)\n"


def test_json_has_events_and_params(tmp_path):
    path = tmp_path / "events.json"
    write_json(EVENTS, path, "ep.mp3", {"z": 6.0})
    data = json.loads(path.read_text())
    assert data["input"] == "ep.mp3"
    assert data["params"] == {"z": 6.0}
    assert [e["timestamp"] for e in data["events"]] == ["0:00:05", "0:12:34"]
    assert data["events"][0] == {
        "start": 5.0,
        "end": 5.05,
        "timestamp": "0:00:05",
        "kind": "click",
        "score": 24.7,
        "hits": 1,
    }


def test_empty_report(tmp_path):
    path = tmp_path / "timestamps.txt"
    write_timestamps([], path)
    assert path.read_text() == ""


def test_clip_name():
    assert clip_name(1, EVENTS[0]) == "001_0h12m34s_crackle.mp3"
    long = Event(start=4 * 3600 + 5.9, end=0, score=0, kind="dropout", hits=1)
    assert clip_name(123, long) == "123_4h00m05s_dropout.mp3"


def test_table_ranks_by_score_and_honours_top():
    lines = format_table(EVENTS, top=1).splitlines()
    assert lines[0] == "2 event(s), showing top 1 by score"
    assert len(lines) == 3
    assert lines[2].split() == ["1", "0:00:05", "0.05s", "25", "click", "1"]


def test_natural_key_sorts_episode_numbers():
    names = ["ep10.mp3", "Ep2.mp3", "ep1.mp3", "bonus.mp3"]
    assert sorted(names, key=natural_key) == ["bonus.mp3", "ep1.mp3", "Ep2.mp3", "ep10.mp3"]


def test_summary_counts_per_type_sorted_by_name():
    lines = format_summary([("ep10.mp3", EVENTS), ("ep2.mp3", []), ("ep3.mp3", None)]).splitlines()
    assert lines[0].split() == ["input", "crackle", "click", "clipping", "dropout", "total"]
    assert lines[1].split() == ["ep2.mp3", "0", "0", "0", "0", "0"]
    assert lines[2].split() == ["ep3.mp3", "failed,", "see", "the", "log"]
    assert lines[3].split() == ["ep10.mp3", "1", "1", "0", "0", "2"]
