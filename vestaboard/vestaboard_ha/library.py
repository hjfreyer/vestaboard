"""The art library: the pieces in ``art.py``, the ones on disk, and picking one.

Saved pieces are text files in the app's own data directory -- ``sunrise.txt``
holds a piece named ``sunrise`` -- written in the same square-per-chip form as
``art.py``, so a file can be hand-edited and a piece can be deleted by deleting
it. A file shadows a built-in piece of the same name, since a file is something
somebody put there on purpose.

A directory is a category: ``bedtime/moon.txt`` is the piece ``moon`` in the
``bedtime`` category, and a file sitting in the art directory itself is in
``art``, the category a piece has when nothing says otherwise. Moving a file is
therefore how a saved piece changes category, the same way renaming it is how a
piece is renamed.

``capture`` is the other way in: the board's current state, written out as a new
``capture-N.txt`` in whichever category was asked for, which is what the
gallery's Capture button does, and ``delete`` is the way back out, which is its
Delete button.
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

#: What a category can be called. It is a directory name as well as a label, so
#: it has to be one plain word and nothing that walks out of the art directory.
CATEGORY_NAME = re.compile(r"[\w-]{1,32}")


def category_asked_for(category: str | None) -> str:
    """The category a caller means, with nothing at all meaning the default.

    An automation's template that renders to nothing while it has no category to
    give is the same as leaving the key out, so blanks count as nothing.
    """
    asked = "" if category is None else str(category).strip()
    return asked or art.DEFAULT_CATEGORY


class Capture(NamedTuple):
    """What ``capture`` did: the piece's name, and whether it is new."""

    name: str
    is_new: bool


class Library:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._last_shown: str | None = None

    def files(self) -> dict[str, Path]:
        """Every saved piece's file by name: the default category, then the rest.

        A name is a name whatever category it is in, so a piece in a directory
        that shares a name with one at the top level is the one that loses.
        """
        paths: dict[str, Path] = {}
        for path in sorted(self.directory.glob(f"*{SUFFIX}")):
            paths[path.stem] = path

        for path in sorted(self.directory.glob(f"*/*{SUFFIX}")):
            if not CATEGORY_NAME.fullmatch(path.parent.name):
                _LOGGER.warning(
                    "%s is not a category, so %s is not a piece", path.parent, path
                )
                continue
            if path.stem in paths:
                _LOGGER.warning(
                    "%s is already the piece %s; keeping %s",
                    path,
                    path.stem,
                    paths[path.stem],
                )
                continue
            paths[path.stem] = path
        return paths

    def category_of(self, path: Path) -> str:
        """The category a file is in: its directory, or the default at the top."""
        if path.parent == self.directory:
            return art.DEFAULT_CATEGORY
        return path.parent.name

    def saved(self) -> dict[str, art.Piece]:
        """Every piece on disk, by name. An empty directory is not a problem."""
        pieces = {}
        for name, path in self.files().items():
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                _LOGGER.warning("cannot read %s: %s", path, exc)
                continue
            except UnicodeDecodeError:
                _LOGGER.warning("%s is not text; skipping it", path)
                continue
            # However the file was written; the parser wants bare newlines.
            pieces[name] = art.Piece(
                text.replace("\r\n", "\n"), self.category_of(path)
            )
        return pieces

    def pieces(self) -> dict[str, art.Piece]:
        """Everything showable: the built-in pieces first, then the saved ones."""
        return art.ARTWORKS | self.saved()

    def grid(
        self, name: str | None = None, category: str | None = None
    ) -> list[list[int]]:
        """Encode the named piece, or a random one from the category.

        A name is a name whatever category the piece is in, so asking for one by
        name says everything and the category is not consulted. Without a name
        the pick is made within the category, which is ``art`` unless the caller
        asks for another.
        """
        pieces = self.pieces()
        if name is None:
            name = self._choose(pieces, category_asked_for(category))
        elif name not in pieces:
            known = ", ".join(sorted(pieces))
            raise ValueError(f"no artwork named {name!r}; there is {known}")

        self._last_shown = name
        _LOGGER.info("showing %s", name)
        return art.to_grid(pieces[name].art)

    def capture(self, grid: list[list[int]], category: str | None = None) -> Capture:
        """Save a grid as a new piece, or name the one that already holds it.

        The category is the directory it lands in, and is what makes the same
        board captured into ``bedtime`` a new piece when it is already saved as
        an ``art`` one: they are two pieces, shown at different times of day.
        """
        category = category_asked_for(category)
        if not CATEGORY_NAME.fullmatch(category):
            raise ValueError(
                f"{category!r} cannot be a category; a category is one plain word"
            )
        if all(code == charcodes.BLANK for row in grid for code in row):
            raise ValueError("the board is blank, so there is nothing to capture")

        text = art.render(grid)
        for name, piece in self.saved().items():
            if piece.art == text and piece.category == category:
                return Capture(name, is_new=False)

        name = self._next_name()
        directory = self.directory_for(category)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{name}{SUFFIX}").write_text(text, encoding="utf-8")
        _LOGGER.info("captured the board as %s in %s", name, category)
        return Capture(name, is_new=True)

    def directory_for(self, category: str) -> Path:
        """Where a category's files live; the default one is the top level."""
        if category == art.DEFAULT_CATEGORY:
            return self.directory
        return self.directory / category

    def delete(self, name: str) -> None:
        """Throw a saved piece away. The file is the piece, so the file goes."""
        path = self.files().get(name)
        if path is None:
            if name in art.ARTWORKS:
                raise ValueError(
                    f"{name} is written into art.py rather than saved, so there "
                    "is no file to delete"
                )
            raise ValueError(f"there is no saved piece named {name!r}")

        # The path came from a file of ours in the first place, so this can only
        # be that file; missing_ok covers it having gone in the meantime.
        path.unlink(missing_ok=True)
        _LOGGER.info("deleted %s", name)

    def _choose(self, pieces: dict[str, art.Piece], category: str) -> str:
        """A piece at random from the category, never the one already up."""
        usable = []
        for name, piece in pieces.items():
            if piece.category != category:
                continue
            try:
                art.to_grid(piece.art)
            except ValueError as exc:
                # A hand-edited file should cost us that piece, not the rotation.
                _LOGGER.warning("leaving %s out; it does not encode: %s", name, exc)
                continue
            usable.append(name)

        if not usable:
            stocked = sorted({piece.category for piece in pieces.values()})
            if not stocked:
                raise ValueError("there is no art to show")
            raise ValueError(
                f"there is no art to show in the {category!r} category; "
                f"there is {', '.join(stocked)}"
            )

        # Never twice in a row: a board that changes every half hour should
        # look like it changed.
        fresh = [name for name in usable if name != self._last_shown]
        return random.choice(fresh or usable)

    def _next_name(self) -> str:
        """One past the highest capture there has been, so names are not reused.

        Captures are numbered across the categories together, since a name is a
        name wherever its file sits.
        """
        taken = [
            int(match.group(1))
            for path in self.files().values()
            if (match := _CAPTURE_NAME.fullmatch(path.stem))
        ]
        return f"{CAPTURE_PREFIX}{max(taken, default=0) + 1}"
