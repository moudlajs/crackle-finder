"""Report writers: pasteable timestamps, Audacity labels, JSON and the overview plot."""

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import numpy as np
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, MultipleLocator
from scipy.signal import spectrogram

from crackle_finder import __version__
from crackle_finder.detect import CLICK, CLIPPING, CRACKLE, DROPOUT, FRAME_SECONDS, KINDS, Event


def format_timestamp(t: float) -> str:
    """Seconds -> ``H:MM:SS``, rounded down so the listener lands just before the event."""
    total = int(t)
    return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"


def safe_name(name: str, max_len: int = 80) -> str:
    """Turn an arbitrary title or filename into a safe, readable folder name."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_name).strip("._-")
    return cleaned[:max_len].rstrip("._-") or "untitled"


def clip_name(rank: int, event: Event) -> str:
    """``001_0h12m34s_crackle.mp3``: rank by score, event start, kind."""
    total = int(event.start)
    h, m, sec = total // 3600, total % 3600 // 60, total % 60
    return f"{rank:03d}_{h}h{m:02d}m{sec:02d}s_{event.kind}.mp3"


def format_table(events: list[Event], top: int) -> str:
    """The ``top`` highest-scoring events as a plain-text table."""
    shown = by_score(events)[:top]
    lines = [
        f"{len(events)} event(s), showing top {len(shown)} by score",
        f"{'#':>4}  {'time':>8}  {'length':>6}  {'score':>6}  {'type':<8}  frames",
    ]
    lines += [
        f"{rank:>4}  {format_timestamp(e.start):>8}  {e.end - e.start:5.2f}s  {e.score:6.0f}"
        f"  {e.kind:<8}  {e.hits:>6}"
        for rank, e in enumerate(shown, 1)
    ]
    return "\n".join(lines)


def natural_key(name: str) -> list:
    """Sort key that puts ``ep2`` before ``ep10``."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def format_summary(results: list[tuple[str, list[Event] | None]]) -> str:
    """Event count per type per input, natural-sorted by name; ``None`` marks a failed input."""
    rows = sorted(results, key=lambda r: natural_key(r[0]))
    width = max([len("input"), *(len(name) for name, _ in rows)])
    lines = [f"{'input':<{width}}  " + "  ".join(f"{k:>8}" for k in (*KINDS, "total"))]
    for name, events in rows:
        if events is None:
            lines.append(f"{name:<{width}}  failed, see the log")
            continue
        counts = [sum(e.kind == k for e in events) for k in KINDS] + [len(events)]
        lines.append(f"{name:<{width}}  " + "  ".join(f"{c:>8}" for c in counts))
    return "\n".join(lines)


def by_time(events: list[Event]) -> list[Event]:
    return sorted(events, key=lambda e: e.start)


def by_score(events: list[Event]) -> list[Event]:
    return sorted(events, key=lambda e: e.score, reverse=True)


def write_timestamps(events: list[Event], path: Path) -> None:
    """One line per event, sorted by time, ready to paste into a message."""
    lines = [
        f"{format_timestamp(e.start)}  {e.kind}  (score {e.score:.0f})" for e in by_time(events)
    ]
    path.write_text("".join(line + "\n" for line in lines))


def write_labels(events: list[Event], path: Path) -> None:
    """Audacity label track: File > Import > Labels."""
    lines = [f"{e.start:.3f}\t{e.end:.3f}\t{e.kind} ({e.score:.0f})" for e in by_time(events)]
    path.write_text("".join(line + "\n" for line in lines))


def write_json(events: list[Event], path: Path, source: str, params: dict[str, Any]) -> None:
    """Machine-readable events plus the parameters of the run."""
    data = {
        "tool": "crackle-finder",
        "version": __version__,
        "input": source,
        "params": params,
        "events": [
            {
                "start": round(e.start, 3),
                "end": round(e.end, 3),
                "timestamp": format_timestamp(e.start),
                "kind": e.kind,
                "score": round(e.score, 2),
                "hits": e.hits,
            }
            for e in by_time(events)
        ],
    }
    path.write_text(json.dumps(data, indent=2) + "\n")


# Categorical slots validated all-pairs for colour-vision deficiency. Every type
# also gets its own labelled row, so identity never relies on colour alone.
COLORS = {CLICK: "#2a78d6", CRACKLE: "#eb6834", DROPOUT: "#1baf7a", CLIPPING: "#4a3aa7"}
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e4e3df"
ENVELOPE = "#a9a8a2"
ENVELOPE_LIGHT = "#dcdbd6"

THUMBNAILS = 6
THUMB_SECONDS = 1.0
MAX_BINS = 1500


def _style(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8, length=0)


def _clock(seconds: float, _pos=None) -> str:
    return format_timestamp(max(seconds, 0.0))


def _tick_step(duration: float, max_ticks: int = 10) -> float:
    """A round clock step (1 s ... 1 h) giving at most ``max_ticks`` ticks."""
    for step in (1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600):
        if duration / step <= max_ticks:
            return step
    return 3600 * (duration // (3600 * max_ticks) + 1)


def _envelope(x: np.ndarray, sr: int, max_bins: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-bin min and max of frame loudness in dBFS, and bin start times (s)."""
    n = int(FRAME_SECONDS * sr)
    frames = len(x) // n
    X = x[: frames * n].reshape(frames, n)
    # einsum squares and sums without a full-size temporary copy of a multi-hour signal.
    rms = np.sqrt(np.einsum("ij,ij->i", X, X, dtype=np.float64) / n)
    db = 20 * np.log10(rms + 1e-9)
    per_bin = max(1, -(-frames // max_bins))
    bins = frames // per_bin
    db = db[: bins * per_bin].reshape(bins, per_bin)
    return db.min(1), db.max(1), np.arange(bins) * per_bin * FRAME_SECONDS


def write_overview(
    x: np.ndarray, sr: int, events: list[Event], path: Path, offset: float = 0.0, title: str = ""
) -> None:
    """Render the overview of mono signal ``x`` (starting at ``offset`` s) to ``path``."""
    fig = Figure(figsize=(12, 7.5), facecolor=SURFACE, layout="constrained")
    grid = fig.add_gridspec(3, THUMBNAILS, height_ratios=[2.2, 0.9, 1.6])
    env_ax = fig.add_subplot(grid[0, :])
    rug_ax = fig.add_subplot(grid[1, :], sharex=env_ax)
    duration = len(x) / sr

    low, high, times = _envelope(x, sr, MAX_BINS)
    # Light area up to the loudest frame per bin, darker up to the quietest: dips show dropouts.
    env_ax.fill_between(offset + times, -80, high, color=ENVELOPE_LIGHT, linewidth=0, step="post")
    env_ax.fill_between(offset + times, -80, low, color=ENVELOPE, linewidth=0, step="post")
    env_ax.set_ylim(-80, 0)
    env_ax.set_ylabel("loudness (dBFS)", color=MUTED, fontsize=9)
    env_ax.grid(axis="y", color=GRID, linewidth=0.8)
    env_ax.tick_params(labelbottom=False)
    _style(env_ax)
    heading = f"{title}  ·  " if title else ""
    env_ax.set_title(
        f"{heading}{len(events)} event(s) in {format_timestamp(offset)}"
        f"\u2013{format_timestamp(offset + duration)}",
        loc="left",
        color=INK,
        fontsize=11,
    )

    # Event markers: one labelled row per type under the envelope, on the same time axis.
    # Position is the identity, colour only reinforces it.
    rows = list(reversed(KINDS))
    for row, kind in enumerate(rows):
        starts = [e.start for e in events if e.kind == kind]
        rug_ax.scatter(
            starts, [row] * len(starts), s=140, color=COLORS[kind], marker="|", linewidths=2
        )
    rug_ax.set_yticks(range(len(rows)), rows)
    rug_ax.set_ylim(-0.6, len(rows) - 0.4)
    rug_ax.set_xlim(offset, offset + duration)
    rug_ax.xaxis.set_major_locator(MultipleLocator(_tick_step(duration)))
    rug_ax.xaxis.set_major_formatter(FuncFormatter(_clock))
    rug_ax.grid(axis="y", color=GRID, linewidth=0.8)
    _style(rug_ax)

    top = by_score(events)[:THUMBNAILS]
    for i in range(THUMBNAILS):
        ax = fig.add_subplot(grid[2, i])
        _style(ax)
        if i >= len(top):
            ax.axis("off")
            continue
        _thumbnail(ax, x, sr, offset, top[i], i + 1)
        if i == 0:
            ax.set_ylabel("kHz", color=MUTED, fontsize=8)

    fig.savefig(path, dpi=110, facecolor=SURFACE)


def _thumbnail(ax, x: np.ndarray, sr: int, offset: float, event: Event, rank: int) -> None:
    middle = (event.start + event.end) / 2 - offset
    lo = max(0, int((middle - THUMB_SECONDS / 2) * sr))
    hi = min(len(x), int((middle + THUMB_SECONDS / 2) * sr))
    t0 = offset + lo / sr
    # Short windows keep a single-sample click visible as a sharp vertical stripe.
    freqs, times, power = spectrogram(x[lo:hi].astype(np.float64), fs=sr, nperseg=256, noverlap=0)
    if power.size:
        db = 10 * np.log10(power + 1e-20)
        top = np.percentile(db, 99.5)
        ax.pcolormesh(t0 + times, freqs, db, cmap="Blues", vmin=top - 60, vmax=top, shading="auto")
    # A marker above the event instead of lines over it, so the defect stays visible.
    ax.axvspan(event.start, event.end, ymin=0.94, ymax=1, color=COLORS[event.kind], linewidth=0)
    ax.set_xlim(t0, offset + hi / sr)
    ax.set_ylim(0, 20000)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v / 1000:.0f}"))
    ax.set_xticks([])
    ax.set_xlabel(f"#{rank} {format_timestamp(event.start)} {event.kind}", color=INK, fontsize=8)
