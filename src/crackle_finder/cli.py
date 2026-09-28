"""Command-line interface: argument parsing and orchestration only."""

import argparse
import logging
import sys
from pathlib import Path

from crackle_finder import CrackleFinderError, __version__, audio, detect, report

log = logging.getLogger("crackle_finder")


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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="crackle-finder",
        description="Find crackles, clicks, clipping and short dropouts in long recordings.",
    )
    p.add_argument("inputs", nargs="+", metavar="INPUT", help="audio file(s) to analyze")
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
        "--out",
        type=Path,
        default=Path("crackle-report"),
        metavar="DIR",
        help="report directory, one subfolder per input (default: %(default)s)",
    )
    p.add_argument("--verbose", action="store_true", help="show debug output")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def analyze(path: Path, args: argparse.Namespace) -> Path:
    """Analyze one file and write its report folder. Returns the folder."""
    if not path.is_file():
        raise CrackleFinderError(f"{path}: no such file")
    log.info("Analyzing %s", path)
    x = audio.load_mono(str(path), detect.SAMPLE_RATE, args.start, args.end)
    log.debug("Decoded %.1f s of audio", len(x) / detect.SAMPLE_RATE)
    events = detect.detect(x, detect.SAMPLE_RATE, offset=args.start, z=args.z, merge=args.merge)

    out = args.out / report.safe_name(path.stem)
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
    print(f"{path.name}: {len(events)} event(s) -> {out}/")
    if not events:
        log.info("Nothing found. Try a lower --z (e.g. 4) for more sensitivity.")
    return out


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
        for name in args.inputs:
            analyze(Path(name), args)
    except CrackleFinderError as e:
        log.error("%s", e)
        return 1
    return 0
