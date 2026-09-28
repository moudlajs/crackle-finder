# Contributing

## Setup

```sh
brew install ffmpeg   # or: sudo apt install ffmpeg
uv sync
```

## Checks (run before every push; CI runs the same)

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

## Pull requests

`main` is protected: changes land through pull requests with green CI.

1. Branch `<type>/<short-desc>` (e.g. `feat/clips`), Conventional Commit PR title.
2. Open the PR as a draft and iterate while CI runs.
3. Mark it ready (`gh pr ready`). That triggers an automated Claude review.
4. Address every review comment: fix it, or reply briefly why not.
5. Squash-merge once CI is green and the review is addressed.

## Rules

- Test audio is synthetic only (`tests/synth.py`). Never commit audio from real
  podcasts or videos.
- Tests never hit the network; mock `yt-dlp`.
- Detection thresholds and the algorithm are a deliberate port of
  `tests/reference/find_crackles.py`; `tests/test_regression.py` guards it.
  Changing them needs a discussion first.
- Runtime dependencies are numpy, scipy and matplotlib. Discuss before adding one.
