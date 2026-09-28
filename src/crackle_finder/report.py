"""Report writers: pasteable timestamps, Audacity labels and JSON."""

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from crackle_finder import __version__
from crackle_finder.detect import Event


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
