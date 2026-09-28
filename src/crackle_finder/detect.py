"""Detection of crackles, clicks, clipping and dropouts.

Pure functions on numpy arrays, no I/O. The algorithm is a straight port of the
original ``find_crackles.py`` prototype (kept in ``tests/reference``); a regression
test checks both produce the same events.
"""

from dataclasses import dataclass

import numpy as np
from scipy.signal import butter, sosfilt

from crackle_finder import CrackleFinderError

SAMPLE_RATE = 44100
FRAME_SECONDS = 0.05
DEFAULT_Z = 6.0
DEFAULT_MERGE = 1.0

HF_CUTOFF_HZ = 5000
CLIP_LEVEL = 0.985
CLIP_MIN_SAMPLES = 3
DROPOUT_DB = -60
LOUD_DB = -35
DROPOUT_BONUS = 5
MIN_FRAMES = 10
EPS = 1e-9

CRACKLE, CLICK, CLIPPING, DROPOUT = "crackle", "click", "clipping", "dropout"
KINDS = (CRACKLE, CLICK, CLIPPING, DROPOUT)


@dataclass(frozen=True)
class Event:
    """A merged run of flagged frames. Times are seconds in the original file."""

    start: float
    end: float
    score: float
    kind: str
    hits: int


def robust_z(v: np.ndarray) -> np.ndarray:
    """Outlier-resistant z-score using the median and MAD instead of mean and std."""
    med = np.median(v)
    mad = np.median(np.abs(v - med)) * 1.4826 + EPS
    return (v - med) / mad


def frame_scores(
    x: np.ndarray, sr: int = SAMPLE_RATE, frame: float = FRAME_SECONDS, z: float = DEFAULT_Z
) -> tuple[np.ndarray, np.ndarray]:
    """Score every frame of mono signal ``x``. Returns ``(score, kind)`` arrays.

    A frame is suspicious when its score exceeds ``z``. Trailing samples that do
    not fill a whole frame are ignored.
    """
    n = int(frame * sr)
    frames = len(x) // n
    if frames < MIN_FRAMES:
        raise CrackleFinderError(
            f"Recording is too short: need at least {MIN_FRAMES * frame:g} s of audio."
        )
    x = x[: frames * n]
    X = x.reshape(frames, n)

    rms = np.sqrt((X**2).mean(1)) + EPS
    db = 20 * np.log10(rms)

    # Digital silence gives log(0) = -inf below; those frames just never score high.
    with np.errstate(divide="ignore", invalid="ignore"):
        # Crackle: sharp peaks above 5 kHz (high crest factor of the HF band).
        sos = butter(4, HF_CUTOFF_HZ, "highpass", fs=sr, output="sos")
        hf = sosfilt(sos, x).reshape(frames, n)
        hf_crest = np.abs(hf).max(1) / (np.sqrt((hf**2).mean(1)) + EPS)
        z_crest = robust_z(np.log(hf_crest))

        # Click: a jump between neighbouring samples out of proportion to the frame level.
        jump = np.abs(np.diff(x, prepend=x[0])).reshape(frames, n).max(1)
        z_jump = robust_z(np.log(jump / rms + EPS))

    # Clipping: samples at the edge of full scale.
    clip = (np.abs(X) > CLIP_LEVEL).sum(1)

    # Dropout: a silent frame between two loud ones.
    prev = np.r_[db[0], db[:-1]]
    nxt = np.r_[db[1:], db[-1]]
    dropout = (db < DROPOUT_DB) & (prev > LOUD_DB) & (nxt > LOUD_DB)

    clipped = clip >= CLIP_MIN_SAMPLES
    score = np.maximum(z_crest, z_jump)
    kind = np.where(z_crest >= z_jump, CRACKLE, CLICK)
    kind = np.where(clipped, CLIPPING, kind)
    kind = np.where(dropout, DROPOUT, kind)
    score = np.where(clipped, np.maximum(score, z + clip), score)
    score = np.where(dropout, np.maximum(score, z + DROPOUT_BONUS), score)
    return score, kind


def merge_frames(flagged: np.ndarray, gap: int) -> list[tuple[int, int]]:
    """Group sorted frame indices into ``(first, last)`` runs.

    Indices at most ``gap`` apart end up in the same run.
    """
    if len(flagged) == 0:
        return []
    runs, start, last = [], int(flagged[0]), int(flagged[0])
    for i in flagged[1:]:
        if i - last > gap:
            runs.append((start, last))
            start = int(i)
        last = int(i)
    runs.append((start, last))
    return runs


def detect(
    x: np.ndarray,
    sr: int = SAMPLE_RATE,
    *,
    offset: float = 0.0,
    frame: float = FRAME_SECONDS,
    z: float = DEFAULT_Z,
    merge: float = DEFAULT_MERGE,
) -> list[Event]:
    """Find events in mono signal ``x``, sorted by start time.

    ``offset`` is where ``x`` starts in the original file, so reported times stay
    relative to the original even when only a section was decoded.
    """
    score, kind = frame_scores(x, sr, frame, z)
    flagged = np.flatnonzero(score > z)

    events = []
    for s, e in merge_frames(flagged, int(merge / frame)):
        seg = score[s : e + 1]
        peak = s + int(np.argmax(seg))
        events.append(
            Event(
                start=offset + s * frame,
                end=offset + (e + 1) * frame,
                score=float(score[peak]),
                kind=str(kind[peak]),
                hits=int((seg > z).sum()),
            )
        )
    return events
