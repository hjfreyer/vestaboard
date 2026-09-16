"""The art library: the pieces in ``art.py``, the ones on disk, and picking one.

Saved pieces are text files in the app's own data directory -- ``sunrise.txt``
holds a piece named ``sunrise`` -- written in the same square-per-chip form as
``art.py``, so a file can be hand-edited and a piece can be deleted by deleting
it. A file shadows a built-in piece of the same name, since a file is something
somebody put there on purpose.

``capture`` is the other way in: the board's current state, written out as a new
``capture-N.txt``, which is what the gallery's Capture button does, and
``delete`` is the way back out, which is its Delete button.
"""

from __future__ import annotations

import logging
import random
import re
from pathlib import Path
from typing import NamedTuple

from . import art, charcodes

_LOGGER = logging.getLogger(__name__)

SUFFIX = ".txt"
CAPTURE_PREFIX = "capture-"

_CAPTURE_NAME = re.compile(rf"{CAPTURE_PREFIX}(\d+)")


class Capture(NamedTuple):
    """What ``capture`` did: the piece's name, and whether it is new."""

    name: str
    is_new: bool


class Library:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._last_shown: str | None = None

    @property
    def last_shown(self) -> str | None:
        """The name of the piece ``grid`` last encoded, which is what is up."""
        return self._last_shown

    def saved(self) -> dict[str, str]:
        """Every piece on disk, by name. An empty directory is not a problem."""
        pieces = {}
        for path in sorted(self.directory.glob(f"*{SUFFIX}")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                _LOGGER.warning("cannot read %s: %s", path, exc)
                continue
            except UnicodeDecodeError:
                _LOGGER.warning("%s is not text; skipping it", path)
                continue
            # However the file was written; the parser wants bare newlines.
            pieces[path.stem] = text.replace("\r\n", "\n")
        return pieces

    def pieces(self) -> dict[str, str]:
        """Everything showable: the built-in pieces first, then the saved ones."""
        return art.ARTWORKS | self.saved()

    def grid(self, name: str | None = None) -> list[list[int]]:
        """Encode the named piece, or one at random when the name is None."""
        pieces = self.pieces()
        if name is None:
            name = self._choose(pieces)
        elif name not in pieces:
            known = ", ".join(sorted(pieces))
            raise ValueError(f"no artwork named {name!r}; there is {known}")

        self._last_shown = name
        _LOGGER.info("showing %s", name)
        return art.to_grid(pieces[name])

    def capture(self, grid: list[list[int]]) -> Capture:
        """Save a grid as a new piece, or name the one that already holds it."""
        if all(code == charcodes.BLANK for row in grid for code in row):
            raise ValueError("the board is blank, so there is nothing to capture")

        text = art.render(grid)
        for name, piece in self.saved().items():
            if piece == text:
                return Capture(name, is_new=False)

        name = self._next_name()
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / f"{name}{SUFFIX}").write_text(text, encoding="utf-8")
        _LOGGER.info("captured the board as %s", name)
        return Capture(name, is_new=True)

    def delete(self, name: str) -> None:
        """Throw a saved piece away. The file is the piece, so the file goes."""
        if name not in self.saved():
            if name in art.ARTWORKS:
                raise ValueError(
                    f"{name} is written into art.py rather than saved, so there "
                    "is no file to delete"
                )
            raise ValueError(f"there is no saved piece named {name!r}")

        # The name came from a file of ours in the first place, so this can only
        # be that file; missing_ok covers it having gone in the meantime.
        (self.directory / f"{name}{SUFFIX}").unlink(missing_ok=True)
        _LOGGER.info("deleted %s", name)

    def _choose(self, pieces: dict[str, str]) -> str:
        """A piece at random, never the one already on the board."""
        usable = []
        for name, piece in pieces.items():
            try:
                art.to_grid(piece)
            except ValueError as exc:
                # A hand-edited file should cost us that piece, not the rotation.
                _LOGGER.warning("leaving %s out; it does not encode: %s", name, exc)
                continue
            usable.append(name)

        if not usable:
            raise ValueError("there is no art to show")

        # Never twice in a row: a board that changes every half hour should
        # look like it changed.
        fresh = [name for name in usable if name != self._last_shown]
        return random.choice(fresh or usable)

    def _next_name(self) -> str:
        """One past the highest capture there has been, so names are not reused."""
        taken = [
            int(match.group(1))
            for path in self.directory.glob(f"{CAPTURE_PREFIX}*{SUFFIX}")
            if (match := _CAPTURE_NAME.fullmatch(path.stem))
        ]
        return f"{CAPTURE_PREFIX}{max(taken, default=0) + 1}"
