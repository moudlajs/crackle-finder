"""Regenerate docs/overview.png and the README sample output from synthetic audio.

    uv run python docs/make_example.py

Only synthetic audio is used: never put real recordings in this repository.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tests"))

from synth import SR, speech_like, write_wav

DOCS = Path(__file__).parent


def main() -> None:
    x = speech_like(12 * 60, seed=42)
    for t in (95.3, 96.1, 97.4, 412.8, 413.5, 655.0):  # a crackly patch, a click, another
        x[int(t * SR)] += 0.5
    for t in (301.0, 302.6):  # clipped shouting
        i = int(t * SR)
        x[i : i + int(0.4 * SR)] = (x[i : i + int(0.4 * SR)] * 15).clip(-1, 1)
    i = int(540.0 * SR)  # a 60 ms dropout
    x[i : i + int(0.06 * SR)] = 0

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "episode-42.wav"
        write_wav(wav, x)
        cmd = ["crackle-finder", str(wav), "--out", tmp, "--no-clips"]
        subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
        (DOCS / "overview.png").write_bytes(
            (Path(tmp) / "episode-42" / "overview.png").read_bytes()
        )
        print((Path(tmp) / "episode-42" / "timestamps.txt").read_text())


if __name__ == "__main__":
    main()
