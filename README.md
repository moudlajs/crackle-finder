# crackle-finder

Find crackles, clicks, clipping and short dropouts in long spoken-word recordings
(podcasts, interviews, lectures) and get a list of timestamps, instead of listening
to two hours of audio to find them.

> Work in progress: full documentation lands with v0.1.0.

## Install

Requires [ffmpeg](https://ffmpeg.org/) on your `PATH`.

```sh
uv tool install git+https://github.com/moudlajs/crackle-finder
```

## Usage

```sh
crackle-finder episode.mp3
crackle-finder episode.mp3 --start 45:00 --end 1:05:30 --z 5
crackle-finder https://example.com/episode-42   # needs yt-dlp
crackle-finder episodes/                        # every audio file in the folder
crackle-finder episode.mp3 --fix                # also write a repaired copy
```

A directory analyzes every audio file in it and writes `summary.txt` with the event
count per type per file, sorted by name, so you can see from which episode a problem
started.

`--fix` writes `fixed.flac` next to the report using ffmpeg's `adeclick` and `adeclip`
filters on the whole file. The original is never modified. Dropouts are missing audio
and cannot be fixed this way.

A URL is downloaded once with [yt-dlp](https://github.com/yt-dlp/yt-dlp) into
`~/.cache/crackle-finder` and reused on later runs; the report is named after its title.

Reports are written to `./crackle-report/<input-name>/`:
`timestamps.txt` (paste into a message), `labels.txt` (Audacity label track),
`events.json`, and `clips/` with a 3 s mp3 of each of the top `--top` events
(skip with `--no-clips`), and `overview.png`: the loudness envelope with event
markers by type plus spectrograms of the top 6 events (skip with `--no-plot`).
The top events are also printed as a table.

## License

MIT
