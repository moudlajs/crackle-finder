import os
import shutil

import pytest
from synth import with_defects, write_wav

# In CI ffmpeg must exist, so a missing binary fails there instead of silently skipping.
needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None and not os.environ.get("CI"), reason="ffmpeg not installed"
)


@pytest.fixture(scope="session")
def defects():
    return with_defects()


@pytest.fixture
def defects_wav(tmp_path, defects):
    path = tmp_path / "episode 01.wav"
    write_wav(path, defects.audio)
    return path
