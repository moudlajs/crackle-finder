# crackle-finder

CLI that finds crackles, clicks, clipping and short dropouts in long spoken-word
recordings. Python 3.11+, uv, ffmpeg. See CONTRIBUTING.md for checks and PR flow.

## Layout

- `src/crackle_finder/cli.py`: argparse + orchestration only
- `audio.py`: ffmpeg (decode to mono float32 at 44.1 kHz, cut mp3 clips)
- `detect.py`: pure numpy functions, no I/O
- `report.py`: timestamps.txt, labels.txt (Audacity), events.json, stdout table, clip names, overview.png (matplotlib `Figure`, no pyplot)
- `tests/reference/find_crackles.py`: the original prototype, kept verbatim and
  excluded from ruff; `tests/test_regression.py` runs it and asserts identical events.

## Conventions

- `logging` for diagnostics (stderr), `--verbose` for debug; results on stdout.
- User-facing failures raise `CrackleFinderError`; the CLI prints it and exits 1.
- Reported times are always relative to the original file (`offset=--start`).
- KISS: no config files, plugins, GUI or server.
- Ask before changing detection thresholds/algorithm or adding dependencies.
- Synthetic test audio only; never hit the network in tests.
