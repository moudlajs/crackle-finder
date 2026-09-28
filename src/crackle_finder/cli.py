"""Command-line interface: argument parsing and orchestration only."""

import argparse
import logging
import sys
from pathlib import Path

from crackle_finder import CrackleFinderError, __version__, audio, detect, download, report

log = logging.getLogger("crackle_finder")

CLIP_SECONDS = 3.0
AUDIO_SUFFIXES = {
    ".aac", ".aif", ".aiff", ".flac", ".m4a", ".mka", ".mp3", ".oga", ".ogg", ".opus", ".wav",
    ".wma",
}  # fmt: skip


def parse_time(value: str) -> float:
    """``90``, ``45:00`` or ``1:05:30`` -> seconds."""
    parts = value.strip().split(":")
    if not 1 <= len(parts) <= 3:
        raise argparse.ArgumentTypeError(f"invalid time {value!r}: use S, M:SS or H:MM:SS")
    try:
        numbers = [float(p) for p in parts]
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid time {value!r}: use S, M:SS or H:MM:SS"
        ) from None
    if any(n < 0 for n in numbers) or any(n >= 60 for n in numbers[1:]):
        raise argparse.ArgumentTypeError(
            f"invalid time {value!r}: minutes and seconds must be between 0 and 59"
        )
    return sum(n * 60**i for i, n in enumerate(reversed(numbers)))


def positive_int(value: str) -> int:
    try:
        n = int(value)
    except ValueError:
        n = 0
    if n < 1:
        raise argparse.ArgumentTypeError(f"expected a whole number >= 1, got {value!r}")
    return n


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="crackle-finder",
        description="Find crackles, clicks, clipping and short dropouts in long recordings.",
    )
    p.add_argument(
        "inputs",
        nargs="+",
        metavar="INPUT",
        help="audio file, directory of audio files (batch) or http(s) URL",
    )
    p.add_argument(
        "--start",
        type=parse_time,
        default=0.0,
        metavar="T",
        help="analyze from this time, e.g. 90, 45:00 or 1:05:30",
    )
    p.add_argument(
        "--end",
        type=parse_time,
        default=None,
        metavar="T",
        help="analyze up to this time (default: end of file)",
    )
    p.add_argument(
        "--z",
        type=float,
        default=detect.DEFAULT_Z,
        help="sensitivity threshold; lower finds more (default: %(default)s)",
    )
    p.add_argument(
        "--merge",
        type=float,
        default=detect.DEFAULT_MERGE,
        metavar="SECONDS",
        help="merge detections closer than this (default: %(default)s)",
    )
    p.add_argument(
        "--top",
        type=positive_int,
        default=50,
        metavar="N",
        help="events shown in the table and cut as clips (default: %(default)s)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=Path("crackle-report"),
        metavar="DIR",
        help="report directory, one subfolder per input (default: %(default)s)",
    )
    p.add_argument(
        "--fix",
        action="store_true",
        help="also write fixed.flac (declicked + declipped copy; the original is never touched)",
    )
    p.add_argument("--no-clips", action="store_true", help="don't cut mp3 clips of top events")
    p.add_argument("--no-plot", action="store_true", help="don't render overview.png")
    p.add_argument("--verbose", action="store_true", help="show debug output")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def analyze(path: Path, args: argparse.Namespace, out: Path, name: str) -> list[detect.Event]:
    """Analyze one file and write its report into folder ``out``. Returns the events."""
    if not path.is_file():
        raise CrackleFinderError(f"{path}: no such file")
    log.info("Analyzing %s", path)
    x = audio.load_mono(str(path), detect.SAMPLE_RATE, args.start, args.end)
    log.debug("Decoded %.1f s of audio", len(x) / detect.SAMPLE_RATE)
    events = detect.detect(x, detect.SAMPLE_RATE, offset=args.start, z=args.z, merge=args.merge)

    out.mkdir(parents=True, exist_ok=True)
    params = {
        "start": args.start,
        "end": args.end,
        "z": args.z,
        "merge": args.merge,
        "frame": detect.FRAME_SECONDS,
        "sample_rate": detect.SAMPLE_RATE,
    }
    report.write_timestamps(events, out / "timestamps.txt")
    report.write_labels(events, out / "labels.txt")
    report.write_json(events, out / "events.json", str(path), params)
    if not args.no_plot:
        log.info("Rendering overview.png")
        report.write_overview(
            x, detect.SAMPLE_RATE, events, out / "overview.png", offset=args.start, title=name
        )
    del x
    if not args.no_clips:
        write_clips(path, events, out / "clips", args.top)
    if args.fix:
        log.info("Writing fixed.flac (whole file; roughly 1 min per 15 min of audio)")
        audio.write_fixed(str(path), str(out / "fixed.flac"))

    print(f"\n{name}: {len(events)} event(s) -> {out}/")
    if events:
        print(report.format_table(events, args.top))
    else:
        log.info("Nothing found. Try a lower --z (e.g. 4) for more sensitivity.")
    return events


def write_clips(src: Path, events: list[detect.Event], folder: Path, top: int) -> None:
    """Cut a short mp3 centred on each of the ``top`` highest-scoring events."""
    folder.mkdir(exist_ok=True)
    for stale in folder.glob("*.mp3"):
        stale.unlink()
    shown = report.by_score(events)[:top]
    log.info("Cutting %d clip(s)", len(shown))
    for rank, e in enumerate(shown, 1):
        middle = (e.start + e.end) / 2
        audio.extract_clip(
            str(src),
            str(folder / report.clip_name(rank, e)),
            middle - CLIP_SECONDS / 2,
            CLIP_SECONDS,
        )


def expand_inputs(items: list[str]) -> list[str]:
    """Replace each directory with the audio files directly inside it, sorted by name."""
    expanded = []
    for item in items:
        folder = Path(item)
        if download.is_url(item) or not folder.is_dir():
            expanded.append(item)
            continue
        files = sorted(
            (p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_SUFFIXES),
            key=lambda p: report.natural_key(p.name),
        )
        if not files:
            raise CrackleFinderError(f"{folder}: no audio files found in this directory")
        expanded += [str(p) for p in files]
    return expanded


def unique_folder(root: Path, name: str, used: set[str]) -> Path:
    """``root/name``, or ``root/name_2`` etc. if another input of this run already took it."""
    candidate, n = name, 1
    while candidate in used:
        n += 1
        candidate = f"{name}_{n}"
    used.add(candidate)
    return root / candidate


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s" if args.verbose else "%(message)s",
        stream=sys.stderr,
    )
    if args.end is not None and args.end <= args.start:
        log.error("--end must be after --start")
        return 2
    try:
        jobs = expand_inputs(args.inputs)
    except CrackleFinderError as e:
        log.error("%s", e)
        return 1

    # One failing input must not stop a batch: log it, carry on, exit 1 at the end.
    results: list[tuple[str, list[detect.Event] | None]] = []
    used: set[str] = set()
    for item in jobs:
        label = item
        try:
            if download.is_url(item):
                path, label = download.fetch(item)
                folder_name = label
            else:
                path = Path(item)
                label, folder_name = path.name, path.stem
            out = unique_folder(args.out, report.safe_name(folder_name), used)
            results.append((label, analyze(path, args, out, label)))
        except CrackleFinderError as e:
            log.error("%s", e)
            results.append((label, None))

    batch = len(jobs) > 1 or any(Path(i).is_dir() for i in args.inputs if not download.is_url(i))
    if batch:
        args.out.mkdir(parents=True, exist_ok=True)
        summary = report.format_summary(results)
        (args.out / "summary.txt").write_text(summary + "\n")
        print(f"\nSummary -> {args.out / 'summary.txt'}\n{summary}")
    return 1 if any(events is None for _, events in results) else 0
