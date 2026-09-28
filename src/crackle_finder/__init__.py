"""Find crackles, clicks, clipping and dropouts in long spoken-word recordings."""

from importlib.metadata import version

__version__ = version("crackle-finder")


class CrackleFinderError(Exception):
    """An error with a message meant for the user; the CLI prints it and exits 1."""
