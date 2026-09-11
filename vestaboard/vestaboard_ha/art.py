"""Pixel art for the board.

Each artwork is a 15x3 block of chips, written inline as three lines of
single-character color codes:

    "sunset": '''
          YYY
       YYOOOOOYY
    OOOORRRRRRROOOO
    '''

A space is a blank chip and the letters in ``PALETTE`` are the six colors,
plus ``W`` white, ``K`` black and ``#`` for a filled (white) chip. Any other
character falls through to ``charcodes.encode_char``, so letters, digits and
punctuation can be mixed in.

Lines are written flush left and may stop early -- the right side is padded
out to 15 -- so no artwork depends on trailing whitespace surviving an editor.
``to_grid`` centers the block on the board's 6x22 grid.
"""

from __future__ import annotations

import logging
import random

from . import charcodes

_LOGGER = logging.getLogger(__name__)

WIDTH = 15
HEIGHT = 3

#: One character per kind of chip. Everything else is a literal character.
PALETTE: dict[str, int] = {
    " ": charcodes.BLANK,
    "R": charcodes.RED,
    "O": charcodes.ORANGE,
    "Y": charcodes.YELLOW,
    "G": charcodes.GREEN,
    "B": charcodes.BLUE,
    "V": charcodes.VIOLET,
    "W": charcodes.WHITE,
    "K": charcodes.BLACK,
    "#": charcodes.FILLED,
}

ARTWORKS: dict[str, str] = {
    "sunset": """
      YYY
   YYOOOOOYY
OOOORRRRRRROOOO
""",
    "heart": """
    RRR RRR
   RRRRRRRRR
     RRRRR
""",
    "rainbow": """
RRROOOYYYGGGBBB
OOOYYYGGGBBBVVV
YYYGGGBBBVVVRRR
""",
    "invader": """
  G  G   G  G
  GGGGGGGGGGG
  G GG   GG G
""",
    "mountain": """
      WWW
    GGGGGGG
  GGGGGGGGGGG
""",
    "flower": """
     VVVVV
     VYYYV
       G
""",
}


def encode_chip(char: str) -> int:
    """Character code for one character of an artwork."""
    if char in PALETTE:
        return PALETTE[char]
    return charcodes.encode_char(char)


def rows(art: str) -> list[str]:
    """The artwork's three lines, each padded out to 15 characters."""
    # Drop the newline after the opening quotes and the one before the closing
    # quotes, and nothing else: a blank top or bottom row is part of the art.
    body = art.removeprefix("\n").removesuffix("\n")
    lines = body.split("\n")
    if len(lines) != HEIGHT:
        raise ValueError(f"artwork has {len(lines)} rows, expected {HEIGHT}")

    padded = []
    for line in lines:
        line = line.rstrip()
        if len(line) > WIDTH:
            raise ValueError(f"{line!r} is wider than {WIDTH} columns")
        padded.append(line.ljust(WIDTH))
    return padded


def to_grid(art: str) -> list[list[int]]:
    """Center an artwork on a 6x22 grid of character codes."""
    top = (charcodes.ROWS - HEIGHT) // 2
    left = (charcodes.COLS - WIDTH) // 2

    grid = charcodes.blank_grid()
    for row, line in enumerate(rows(art)):
        for col, char in enumerate(line):
            grid[top + row][left + col] = encode_chip(char)
    return grid


_last_shown: str | None = None


def grid(name: str | None = None) -> list[list[int]]:
    """Encode the named artwork, or a random one when the name is None."""
    global _last_shown

    if name is None:
        # Never twice in a row: a board that changes every half hour should
        # look like it changed.
        choices = [other for other in ARTWORKS if other != _last_shown]
        name = random.choice(choices or list(ARTWORKS))
    elif name not in ARTWORKS:
        known = ", ".join(sorted(ARTWORKS))
        raise ValueError(f"no artwork named {name!r}; there is {known}")

    _last_shown = name
    _LOGGER.info("showing %s", name)
    return to_grid(ARTWORKS[name])
