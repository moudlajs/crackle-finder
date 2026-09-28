"""yt-dlp wrapper: download the audio of a URL into a cache, once."""

import hashlib
import logging
import os
import shutil
import subprocess
from pathlib import Path

from crackle_finder import CrackleFinderError

log = logging.getLogger(__name__)

YTDLP_HINT = (
    "yt-dlp is required for URL input but was not found on PATH. Install it, e.g. "
    "`brew install yt-dlp` or `uv tool install yt-dlp`, or download the audio yourself "
    "and pass the file."
)
TITLE_FILE = "title.txt"


def is_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "crackle-finder" / "downloads"


def _cached_audio(folder: Path) -> Path | None:
    files = [p for p in folder.glob("audio.*") if p.suffix not in {".part", ".ytdl"}]
    return files[0] if files else None


def fetch(url: str, cache: Path | None = None) -> tuple[Path, str]:
    """Return ``(audio_path, title)`` for ``url``, downloading only on a cache miss."""
    folder = (cache or cache_dir()) / hashlib.sha256(url.encode()).hexdigest()[:16]
    title_file = folder / TITLE_FILE
    audio = _cached_audio(folder)
    if audio and title_file.is_file():
        log.info("Using cached download %s", audio)
        return audio, title_file.read_text().strip()

    ytdlp = shutil.which("yt-dlp")
    if ytdlp is None:
        raise CrackleFinderError(YTDLP_HINT)
    folder.mkdir(parents=True, exist_ok=True)
    cmd = [
        ytdlp, "--no-playlist", "--no-progress", "--format", "bestaudio/best",
        "--output", str(folder / "audio.%(ext)s"), "--no-simulate", "--print", "title",
        "--", url,
    ]  # fmt: skip
    log.info("Downloading %s", url)
    log.debug("Running %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    audio = _cached_audio(folder)
    if proc.returncode != 0 or audio is None:
        detail = proc.stderr.strip() or "no audio file was produced"
        raise CrackleFinderError(f"yt-dlp could not download {url}: {detail}")
    title = proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else audio.stem
    title_file.write_text(title + "\n")
    return audio, title
