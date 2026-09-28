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
```

Reports are written to `./crackle-report/<input-name>/`:
`timestamps.txt` (paste into a message), `labels.txt` (Audacity label track),
`events.json`, and `clips/` with a 3 s mp3 of each of the top `--top` events
(skip with `--no-clips`), and `overview.png`: the loudness envelope with event
markers by type plus spectrograms of the top 6 events (skip with `--no-plot`).
The top events are also printed as a table.

## License

MIT
