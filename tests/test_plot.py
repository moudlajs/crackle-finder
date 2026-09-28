import numpy as np
import pytest
from synth import SR, speech_like

from crackle_finder.detect import KINDS, Event, detect
from crackle_finder.report import _tick_step, write_overview

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def render(tmp_path, x, events, offset=0.0):
    path = tmp_path / "overview.png"
    write_overview(x, SR, events, path, offset=offset, title="test")
    assert path.read_bytes().startswith(PNG_MAGIC)
    return path


def test_overview_with_detected_events(tmp_path, defects):
    render(tmp_path, defects.audio, detect(defects.audio, SR))


def test_overview_with_no_events(tmp_path):
    render(tmp_path, speech_like(20), [])


def test_overview_of_silence(tmp_path):
    render(tmp_path, np.zeros(SR * 5, dtype=np.float32), [])


@pytest.mark.parametrize("start", [0.0, 0.01, 19.95])
def test_thumbnails_at_the_edges(tmp_path, start):
    events = [Event(start=start, end=start + 0.05, score=9, kind=k, hits=1) for k in KINDS]
    render(tmp_path, speech_like(20), events)


def test_overview_of_a_section(tmp_path):
    # x holds 20 s that start 1 h into the original file.
    events = [Event(start=3605.0, end=3605.05, score=9, kind="click", hits=1)]
    render(tmp_path, speech_like(20), events, offset=3600.0)


def test_many_events_long_file(tmp_path):
    x = speech_like(600)
    events = [
        Event(start=t, end=t + 0.05, score=7 + t % 5, kind=KINDS[int(t) % 4], hits=1)
        for t in np.arange(1, 590, 3.7)
    ]
    render(tmp_path, x, events)


@pytest.mark.parametrize(
    ("duration", "step"),
    [(8, 1), (60, 10), (1800, 300), (7200, 900), (36000, 3600), (72000, 10800)],
)
def test_tick_step_is_round_and_sparse(duration, step):
    assert _tick_step(duration) == step
