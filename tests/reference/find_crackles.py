#!/usr/bin/env python3
"""
Nájde v nahrávke miesta s praskaním, clippingom a krátkymi výpadkami.

Výstup:
  - tabuľka v termináli (zoradená podľa závažnosti)
  - <subor>.labels.txt  -> Audacity: File > Import > Labels, potom preskakuješ po značkách

Požiadavky:  brew install ffmpeg && pip install numpy scipy
Použitie:    python3 find_crackles.py epizoda.mp3 [--z 6] [--top 50] [--start 30:00 --end 1:15:00]
"""
import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt


def parse_time(s: str) -> float:
    """'1:05:30', '45:00' alebo '90' -> sekundy."""
    parts = [float(p) for p in s.split(":")]
    return sum(v * 60 ** i for i, v in enumerate(reversed(parts)))


def load_mono(path: str, sr: int, start: float, end: float | None) -> np.ndarray:
    cmd = ["ffmpeg", "-v", "error", "-ss", str(start), "-i", path]
    if end is not None:
        cmd += ["-t", str(end - start)]
    cmd += ["-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    try:
        raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    except FileNotFoundError:
        sys.exit("Chyba: ffmpeg nie je nainštalovaný (brew install ffmpeg).")
    except subprocess.CalledProcessError as e:
        sys.exit(f"Chyba pri dekódovaní: {e.stderr.decode(errors='ignore')}")
    return np.frombuffer(raw, dtype=np.float32)


def robust_z(v: np.ndarray) -> np.ndarray:
    """Z-skóre odolné voči outlierom (medián + MAD)."""
    med = np.median(v)
    mad = np.median(np.abs(v - med)) * 1.4826 + 1e-9
    return (v - med) / mad


def fmt(t: float) -> str:
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("file")
    p.add_argument("--sr", type=int, default=44100)
    p.add_argument("--frame", type=float, default=0.05, help="dĺžka okna v sekundách")
    p.add_argument("--z", type=float, default=6.0, help="citlivosť: nižšie = viac nálezov")
    p.add_argument("--merge", type=float, default=1.0, help="spojí nálezy bližšie ako N sekúnd")
    p.add_argument("--top", type=int, default=50)
    p.add_argument("--start", default="0", help="začiatok úseku, napr. 30:00")
    p.add_argument("--end", default=None, help="koniec úseku, napr. 1:15:00")
    a = p.parse_args()

    t0 = parse_time(a.start)
    t1 = parse_time(a.end) if a.end else None
    if t1 is not None and t1 <= t0:
        sys.exit("Chyba: --end musí byť za --start.")

    x = load_mono(a.file, a.sr, t0, t1)
    n = int(a.frame * a.sr)
    frames = len(x) // n
    if frames < 10:
        sys.exit("Nahrávka je príliš krátka.")
    x = x[: frames * n]
    X = x.reshape(frames, n)
    print(f"Úsek od {fmt(t0)}, dĺžka {fmt(len(x) / a.sr)}, {frames} okien po {a.frame * 1000:.0f} ms")

    rms = np.sqrt((X ** 2).mean(1)) + 1e-9
    db = 20 * np.log10(rms)

    # 1) Praskanie: ostré špičky vo vysokých frekvenciách (vysoký crest factor nad 5 kHz)
    sos = butter(4, 5000, "highpass", fs=a.sr, output="sos")
    hf = sosfilt(sos, x).reshape(frames, n)
    hf_crest = np.abs(hf).max(1) / (np.sqrt((hf ** 2).mean(1)) + 1e-9)
    z_crest = robust_z(np.log(hf_crest))

    # 2) Kliky: skok medzi susednými vzorkami nepomerný k hlasitosti okna
    jump = np.abs(np.diff(x, prepend=x[0])).reshape(frames, n).max(1)
    z_jump = robust_z(np.log(jump / rms + 1e-9))

    # 3) Clipping: vzorky na hranici plného rozsahu
    clip = (np.abs(X) > 0.985).sum(1)

    # 4) Výpadok: náhle ticho medzi dvoma hlasnými oknami
    prev = np.r_[db[0], db[:-1]]
    nxt = np.r_[db[1:], db[-1]]
    dropout = (db < -60) & (prev > -35) & (nxt > -35)

    score = np.maximum(z_crest, z_jump)
    kind = np.where(z_crest >= z_jump, "praskanie", "klik")
    kind = np.where(clip >= 3, "clipping", kind)
    kind = np.where(dropout, "vypadok", kind)
    score = np.where(clip >= 3, np.maximum(score, a.z + clip), score)
    score = np.where(dropout, np.maximum(score, a.z + 5), score)
    flagged = np.where(score > a.z)[0]

    if flagged.size == 0:
        print("Nič nenájdené. Skús nižšie --z (napr. 4).")
        return

    # Spojenie blízkych okien do udalostí
    gap = int(a.merge / a.frame)
    events, start, last = [], flagged[0], flagged[0]
    for i in flagged[1:]:
        if i - last > gap:
            events.append((start, last))
            start = i
        last = i
    events.append((start, last))

    rows = []
    for s, e in events:
        seg = slice(s, e + 1)
        peak = int(s + np.argmax(score[seg]))
        rows.append({
            "start": t0 + s * a.frame,
            "end": t0 + (e + 1) * a.frame,
            "score": float(score[peak]),
            "kind": str(kind[peak]),
            "hits": int((score[seg] > a.z).sum()),
        })

    rows.sort(key=lambda r: r["score"], reverse=True)
    print(f"\nNájdených udalostí: {len(rows)} (zobrazujem top {min(a.top, len(rows))})\n")
    print(f"{'čas':>11}  {'dĺžka':>6}  {'skóre':>6}  {'typ':<10} okien")
    for r in rows[: a.top]:
        print(f"{fmt(r['start']):>11}  {r['end'] - r['start']:5.2f}s  {r['score']:6.1f}  {r['kind']:<10} {r['hits']}")

    labels = Path(a.file).with_suffix(".labels.txt")
    with labels.open("w") as f:
        for r in sorted(rows, key=lambda r: r["start"]):
            f.write(f"{r['start']:.3f}\t{r['end']:.3f}\t{r['kind']} ({r['score']:.0f})\n")
    print(f"\nAudacity značky: {labels}")


if __name__ == "__main__":
    main()
