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
DROPOUT_MAX_FRAMES = 10  # 500 ms; longer silences are treated as pauses, not dropouts
# Each clipped sample adds 1 to the score, up to this many. Uncapped (as in the
# prototype) a clipped frame reaches ~2200 and crowds every other event out of the top N.
CLIP_SCORE_CAP = 20
MIN_FRAMES = 10
CHUNK_FRAMES = 1200  # 60 s at 50 ms frames: bounds the float64 temporaries
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


def frame_features(
    x: np.ndarray, sr: int, n: int, chunk_frames: int = CHUNK_FRAMES
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Per-frame ``(rms, hf_crest, jump, clip)`` of ``x``, whose length is a multiple of ``n``.

    Works through ``chunk_frames`` frames at a time so the float64 temporaries stay
    small on multi-hour files. The high-pass filter state and the previous sample
    carry across chunks, so the result is identical to processing ``x`` in one go.
    """
    frames = len(x) // n
    rms, hf_crest, jump = (np.empty(frames) for _ in range(3))
    clip = np.empty(frames, dtype=np.int64)
    sos = butter(4, HF_CUTOFF_HZ, "highpass", fs=sr, output="sos")
    state = np.zeros((sos.shape[0], 2))
    prev = x[:1]
    for first in range(0, frames, chunk_frames):
        rows = slice(first, min(first + chunk_frames, frames))
        c = x[rows.start * n : rows.stop * n]
        C = c.reshape(-1, n)
        rms[rows] = np.sqrt((C**2).mean(1)) + EPS

        # Crackle: sharp peaks above 5 kHz (high crest factor of the HF band).
        hf, state = sosfilt(sos, c, zi=state)
        hf = hf.reshape(-1, n)
        hf_crest[rows] = np.abs(hf).max(1) / (np.sqrt((hf**2).mean(1)) + EPS)

        # Click: a jump between neighbouring samples out of proportion to the frame level.
        jump[rows] = np.abs(np.diff(c, prepend=prev)).reshape(-1, n).max(1)
        prev = c[-1:]

        # Clipping: samples at the edge of full scale.
        clip[rows] = (np.abs(C) > CLIP_LEVEL).sum(1)
    return rms, hf_crest, jump, clip


def frame_scores(
    x: np.ndarray,
    sr: int = SAMPLE_RATE,
    frame: float = FRAME_SECONDS,
    z: float = DEFAULT_Z,
    chunk_frames: int = CHUNK_FRAMES,
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
    rms, hf_crest, jump, clip = frame_features(x[: frames * n], sr, n, chunk_frames)
    db = 20 * np.log10(rms)

    # Digital silence gives log(0) = -inf below; those frames just never score high.
    with np.errstate(divide="ignore", invalid="ignore"):
        z_crest = robust_z(np.log(hf_crest))
        z_jump = robust_z(np.log(jump / rms + EPS))

    dropout = dropout_frames(db)

    clipped = clip >= CLIP_MIN_SAMPLES
    score = np.maximum(z_crest, z_jump)
    kind = np.where(z_crest >= z_jump, CRACKLE, CLICK)
    kind = np.where(clipped, CLIPPING, kind)
    kind = np.where(dropout, DROPOUT, kind)
    score = np.where(clipped, np.maximum(score, z + np.minimum(clip, CLIP_SCORE_CAP)), score)
    score = np.where(dropout, np.maximum(score, z + DROPOUT_BONUS), score)
    return score, kind


def dropout_frames(db: np.ndarray, max_frames: int = DROPOUT_MAX_FRAMES) -> np.ndarray:
    """Mark runs of 1..``max_frames`` silent frames with a loud frame on both sides.

    Audio that stops abruptly mid-speech and comes back is a dropout; a pause where
    speech fades out first, or a long silence, is not. The prototype's rule is the
    one-frame case. Runs touching either end of the recording never count.
    """
    silent = db < DROPOUT_DB
    loud = db > LOUD_DB
    edges = np.diff(np.r_[0, silent.astype(np.int8), 0])
    dropout = np.zeros(len(db), dtype=bool)
    for first, stop in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1), strict=True):
        if (
            stop - first <= max_frames
            and first > 0
            and stop < len(db)
            and loud[first - 1]
            and loud[stop]
        ):
            dropout[first:stop] = True
    return dropout


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
                kind=event_kind(kind[s : e + 1], str(kind[peak])),
                hits=int((seg > z).sum()),
            )
        )
    return events


def event_kind(kinds: np.ndarray, peak_kind: str) -> str:
    """Label an event with the same precedence a single frame uses.

    Any dropout frame makes it a dropout, else any clipped frame makes it clipping;
    otherwise the peak frame decides between crackle and click. With clipping scores
    capped, a neighbouring crackle frame can outscore the clipped ones, and the event
    would otherwise be mislabelled.
    """
    for kind in (DROPOUT, CLIPPING):
        if kind in kinds:
            return kind
    return peak_kind
