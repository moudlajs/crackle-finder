"""The port must produce exactly the events of the original prototype."""

import subprocess
import sys
from pathlib import Path

import pytest
from conftest import needs_ffmpeg
from synth import SR

from crackle_finder.audio import load_mono
from crackle_finder.detect import detect

PROTOTYPE = Path(__file__).parent / "reference" / "find_crackles.py"
KIND_NAMES = {"praskanie": "crackle", "klik": "click", "clipping": "clipping", "vypadok": "dropout"}


def run_prototype(wav: Path, *extra: str) -> list[tuple[float, float, str, str]]:
    subprocess.run(
        [sys.executable, str(PROTOTYPE), str(wav), *extra], check=True, capture_output=True
    )
    rows = []
    for line in wav.with_suffix(".labels.txt").read_text().splitlines():
        start, end, label = line.split("\t")
        kind, score = label.split(" ")
        rows.append((float(start), float(end), KIND_NAMES[kind], score))
    return rows


def run_port(wav: Path, start: float = 0.0, end: float | None = None, **kw):
    x = load_mono(str(wav), SR, start, end)
    return [
        (round(e.start, 3), round(e.end, 3), e.kind, f"({e.score:.0f})")
        for e in detect(x, SR, offset=start, **kw)
    ]


@needs_ffmpeg
@pytest.mark.parametrize(
    ("proto_args", "port_kw"),
    [
        ((), {}),
        (("--z", "4", "--merge", "0.2"), {"z": 4.0, "merge": 0.2}),
        (("--start", "0:20", "--end", "50"), {"start": 20.0, "end": 50.0}),
    ],
)
def test_port_matches_prototype(defects_wav, proto_args, port_kw):
    start = port_kw.pop("start", 0.0)
    end = port_kw.pop("end", None)
    expected = run_prototype(defects_wav, *proto_args)
    assert expected, "prototype found nothing; the fixture is not exercising detection"
    assert run_port(defects_wav, start, end, **port_kw) == expected
