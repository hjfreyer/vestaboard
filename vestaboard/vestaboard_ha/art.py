"""Pixel art for the board.

Each artwork is 15 chips wide and 3 rows tall, written inline so the source
shows the piece:

    "flower": '''
⬛⬛⬛⬛⬛🟪🟪🟪🟪🟪⬛⬛⬛⬛⬛
⬛⬛⬛⬛⬛🟪🟨🟨🟨🟪⬛⬛⬛⬛⬛
⬛⬛⬛⬛⬛⬛⬛🟩⬛⬛⬛⬛⬛⬛⬛
''',

Every chip takes two columns, because that is what a fixed-width font gives a
colored square. Text has to keep to the same grid, so a character is written as
a space and then the character -- `` P A R T Y`` is five chips, not ten, and a
bare ``PARTY`` is an error. Two spaces are therefore a blank chip, and since
short lines are padded out on the right, trailing blanks can be left off.

``to_grid`` centers the block on the board's 6x22 grid.
"""

from __future__ import annotations

import logging
import random

from . import charcodes

_LOGGER = logging.getLogger(__name__)

WIDTH = 15
HEIGHT = 3

#: Some sources paste the squares with a variation selector attached.
VARIATION_SELECTOR = "\ufe0f"

#: One square per color of chip. ⬛ is the board's off state; a black chip
#: looks no different, so there is no separate square for one.
PALETTE: dict[str, int] = {
    "⬛": charcodes.BLANK,
    "🟥": charcodes.RED,
    "🟧": charcodes.ORANGE,
    "🟨": charcodes.YELLOW,
    "🟩": charcodes.GREEN,
    "🟦": charcodes.BLUE,
    "🟪": charcodes.VIOLET,
    "⬜": charcodes.WHITE,
}

ARTWORKS: dict[str, str] = {
    "sunset": """
⬛⬛⬛⬛⬛⬛🟨🟨🟨⬛⬛⬛⬛⬛⬛
⬛⬛⬛🟨🟨🟧🟧🟧🟧🟧🟨🟨⬛⬛⬛
🟧🟧🟧🟧🟥🟥🟥🟥🟥🟥🟥🟧🟧🟧🟧
""",
    "heart": """
⬛⬛⬛⬛🟥🟥🟥⬛🟥🟥🟥⬛⬛⬛⬛
⬛⬛⬛🟥🟥🟥🟥🟥🟥🟥🟥🟥⬛⬛⬛
⬛⬛⬛⬛⬛🟥🟥🟥🟥🟥⬛⬛⬛⬛⬛
""",
    "rainbow": """
🟥🟥🟥🟧🟧🟧🟨🟨🟨🟩🟩🟩🟦🟦🟦
🟧🟧🟧🟨🟨🟨🟩🟩🟩🟦🟦🟦🟪🟪🟪
🟨🟨🟨🟩🟩🟩🟦🟦🟦🟪🟪🟪🟥🟥🟥
""",
    "invader": """
⬛⬛🟩⬛⬛🟩⬛⬛⬛🟩⬛⬛🟩⬛⬛
⬛⬛🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩⬛⬛
⬛⬛🟩⬛🟩🟩⬛⬛⬛🟩🟩⬛🟩⬛⬛
""",
    "mountain": """
⬛⬛⬛⬛⬛⬛⬜⬜⬜⬛⬛⬛⬛⬛⬛
⬛⬛⬛⬛🟩🟩🟩🟩🟩🟩🟩⬛⬛⬛⬛
⬛⬛🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩⬛⬛
""",
    "flower": """
⬛⬛⬛⬛⬛🟪🟪🟪🟪🟪⬛⬛⬛⬛⬛
⬛⬛⬛⬛⬛🟪🟨🟨🟨🟪⬛⬛⬛⬛⬛
⬛⬛⬛⬛⬛⬛⬛🟩⬛⬛⬛⬛⬛⬛⬛
""",
    "party": """
🟥🟧🟨🟩🟦🟪🟥🟧🟨🟩🟦🟪🟥🟧🟨
⬛⬛⬛⬛ P A R T Y !⬛⬛⬛⬛⬛
🟪🟦🟩🟨🟧🟥🟪🟦🟩🟨🟧🟥🟪🟦🟩
""",
}


def encode_chip(chip: str) -> int:
    """Character code for one chip: a colored square, or a character."""
    if chip in PALETTE:
        return PALETTE[chip]
    return charcodes.encode_char(chip)


def _why_not(char: str) -> str:
    """Why a character cannot start a chip, said usefully."""
    if char.upper() not in charcodes.CHAR_TO_CODE:
        return f"{char!r} is not a chip; the squares are {' '.join(PALETTE)}"
    return (
        f"{char!r} is unpaired: write a character as a space and then the "
        f"character, {' ' + char!r}, to keep it two columns wide"
    )


def cells(line: str) -> list[str]:
    """Split one line of an artwork into chips, two source columns each."""
    line = line.replace(VARIATION_SELECTOR, "").rstrip()

    chips = []
    index = 0
    while index < len(line):
        char = line[index]
        if char in PALETTE:
            chips.append(char)
            index += 1
        elif char == " ":
            # A space and then the character, so text occupies the same two
            # columns a square does. Two spaces are a blank chip.
            chips.append(line[index + 1] if index + 1 < len(line) else " ")
            index += 2
        else:
            raise ValueError(_why_not(char))

    if len(chips) > WIDTH:
        raise ValueError(f"{line!r} is {len(chips)} chips, wider than {WIDTH}")
    return chips


def rows(art: str) -> list[list[str]]:
    """The artwork's three rows, each padded out to 15 chips."""
    # Drop the newline after the opening quotes and the one before the closing
    # quotes, and nothing else: a blank top or bottom row is part of the art.
    body = art.removeprefix("\n").removesuffix("\n")
    lines = body.split("\n")
    if len(lines) != HEIGHT:
        raise ValueError(f"artwork has {len(lines)} rows, expected {HEIGHT}")

    return [chips + [" "] * (WIDTH - len(chips)) for chips in map(cells, lines)]


def to_grid(art: str) -> list[list[int]]:
    """Center an artwork on a 6x22 grid of character codes."""
    top = (charcodes.ROWS - HEIGHT) // 2
    left = (charcodes.COLS - WIDTH) // 2

    grid = charcodes.blank_grid()
    for row, chips in enumerate(rows(art)):
        for col, chip in enumerate(chips):
            grid[top + row][left + col] = encode_chip(chip)
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
