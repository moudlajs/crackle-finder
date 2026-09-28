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
