"""Synthetic speech-like test audio with defects injected at known times."""

from dataclasses import dataclass, field

import numpy as np
from scipy.io import wavfile

SR = 44100


@dataclass
class Synth:
    audio: np.ndarray
    clicks: list[float] = field(default_factory=list)
    clipping: list[float] = field(default_factory=list)
    dropouts: list[float] = field(default_factory=list)


def speech_like(duration: float, seed: int = 0) -> np.ndarray:
    """Harmonic tone plus noise, amplitude-modulated at a syllable-like rate.

    The level stays well above -35 dBFS so a dropout is always "between loud frames".
    """
    rng = np.random.default_rng(seed)
    t = np.arange(int(duration * SR)) / SR
    pitch = 140 + 20 * np.sin(2 * np.pi * 0.3 * t)
    phase = 2 * np.pi * np.cumsum(pitch) / SR
    voice = sum(np.sin(k * phase) / k for k in range(1, 8))
    envelope = 0.6 + 0.4 * np.sin(2 * np.pi * 4 * t) * np.sin(2 * np.pi * 0.7 * t)
    x = 0.08 * envelope * voice + 0.01 * rng.standard_normal(len(t))
    return x.astype(np.float32)


def with_defects(duration: float = 60.0, seed: int = 0) -> Synth:
    x = speech_like(duration, seed).copy()
    s = Synth(x, clicks=[5.012, 17.53, 41.2], clipping=[25.0], dropouts=[33.0])
    for t in s.clicks:
        x[int(t * SR)] += 0.6
    for t in s.clipping:
        i = int(t * SR)
        x[i : i + int(0.3 * SR)] = np.clip(x[i : i + int(0.3 * SR)] * 20, -1, 1)
    for t in s.dropouts:
        i = int(t * SR)
        x[i : i + int(0.06 * SR)] = 0
    return s


def write_wav(path, audio: np.ndarray) -> None:
    wavfile.write(path, SR, audio.astype(np.float32))
