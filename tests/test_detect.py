import numpy as np
import pytest
from synth import SR, speech_like

from crackle_finder import CrackleFinderError
from crackle_finder.detect import (
    CLICK,
    CLIPPING,
    CRACKLE,
    DROPOUT,
    detect,
    merge_frames,
    robust_z,
)

TOLERANCE = 0.1


def near(events, t, kinds):
    return [e for e in events if abs(e.start - t) <= TOLERANCE and e.kind in kinds]


def test_robust_z_centres_on_median_and_scales_by_mad():
    v = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    z = robust_z(v)
    # median 3, MAD 1 -> scaled MAD 1.4826
    assert z[2] == pytest.approx(0.0)
    assert z[4] == pytest.approx(2 / 1.4826, rel=1e-6)


def test_robust_z_ignores_a_huge_outlier():
    v = np.array([1.0, 2.0, 3.0, 4.0, 1000.0])
    assert robust_z(v)[4] > 100


def test_robust_z_constant_input_does_not_divide_by_zero():
    assert np.all(robust_z(np.ones(5)) == 0)


@pytest.mark.parametrize(
    ("flagged", "gap", "expected"),
    [
        ([], 20, []),
        ([7], 20, [(7, 7)]),
        ([1, 2, 3], 0, [(1, 1), (2, 2), (3, 3)]),
        ([1, 2, 3], 1, [(1, 3)]),
        ([1, 21, 42], 20, [(1, 21), (42, 42)]),
    ],
)
def test_merge_frames(flagged, gap, expected):
    assert merge_frames(np.array(flagged, dtype=int), gap) == expected


def test_finds_every_injected_defect(defects):
    events = detect(defects.audio, SR)
    for t in defects.clicks:
        assert near(events, t, {CLICK, CRACKLE}), f"click at {t} s not found"
    for t in defects.clipping:
        assert near(events, t, {CLIPPING}), f"clipping at {t} s not found"
    for t in defects.dropouts:
        assert near(events, t, {DROPOUT}), f"dropout at {t} s not found"
    expected = len(defects.clicks) + len(defects.clipping) + len(defects.dropouts)
    assert len(events) == expected


@pytest.mark.parametrize("seed", range(3))
def test_clean_signal_has_no_events(seed):
    assert detect(speech_like(120, seed), SR) == []


def test_digital_silence_has_no_events():
    assert detect(np.zeros(SR * 5, dtype=np.float32), SR) == []


def test_offset_shifts_times(defects):
    plain = detect(defects.audio, SR)
    shifted = detect(defects.audio, SR, offset=100.0)
    assert [e.start + 100 for e in plain] == pytest.approx([e.start for e in shifted])


def test_merge_joins_close_events(defects):
    # The first two clicks are 12.5 s apart.
    assert len(detect(defects.audio, SR, merge=15.0)) < len(detect(defects.audio, SR))


def test_events_are_sorted_by_time(defects):
    starts = [e.start for e in detect(defects.audio, SR)]
    assert starts == sorted(starts)


def test_too_short_raises():
    with pytest.raises(CrackleFinderError, match="too short"):
        detect(np.zeros(SR // 10, dtype=np.float32), SR)
