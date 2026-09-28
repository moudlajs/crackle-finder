"""ffmpeg wrappers: decoding audio to mono float32."""

import logging
import shutil
import subprocess

import numpy as np

from crackle_finder import CrackleFinderError

log = logging.getLogger(__name__)

FFMPEG_HINT = (
    "ffmpeg is required but was not found on PATH. Install it, e.g. "
    "`brew install ffmpeg` (macOS) or `sudo apt install ffmpeg` (Debian/Ubuntu)."
)


def require_ffmpeg() -> str:
    """Return the ffmpeg path or raise a user-facing error explaining how to install it."""
    path = shutil.which("ffmpeg")
    if path is None:
        raise CrackleFinderError(FFMPEG_HINT)
    return path


def load_mono(path: str, sr: int, start: float = 0.0, end: float | None = None) -> np.ndarray:
    """Decode ``path`` (anything ffmpeg reads) to mono float32 at ``sr`` Hz.

    Only the section from ``start`` to ``end`` seconds is decoded.
    """
    cmd = [require_ffmpeg(), "-nostdin", "-v", "error", "-ss", str(start), "-i", str(path)]
    if end is not None:
        cmd += ["-t", str(end - start)]
    cmd += ["-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    log.debug("Running %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        detail = proc.stderr.decode(errors="replace").strip()
        raise CrackleFinderError(f"ffmpeg could not decode {path}: {detail}")
    return np.frombuffer(proc.stdout, dtype=np.float32)
