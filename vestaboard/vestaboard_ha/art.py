"""Pixel art for the board.

Each artwork is written inline so the source shows the piece:

    "rainbow": '''
🟥🟥🟥🟧🟧🟧🟨🟨🟨🟩🟩🟩🟦🟦🟦
🟧🟧🟧🟨🟨🟨🟩🟩🟩🟦🟦🟦🟪🟪🟪
🟨🟨🟨🟩🟩🟩🟦🟦🟦🟪🟪🟪🟥🟥🟥
''',

Every chip takes two columns, because that is what a fixed-width font gives a
colored square. Text has to keep to the same grid, so a character is written as
a space and then the character -- `` P A R T Y`` is five chips, not ten, and a
bare ``PARTY`` is an error. Two spaces are therefore a blank chip, and since
short lines are padded out on the right, trailing blanks can be left off.

A piece is as wide as its widest line and as tall as its line count, up to the
board's own 15x3, and ``to_grid`` centers it there. A full-size piece -- which
the ones here are, and which a piece captured off the board always is -- lands
on the board exactly as written; a smaller one is centered.

``render`` goes the other way, turning a grid back into text to save.
"""

from __future__ import annotations

import logging

from . import charcodes

_LOGGER = logging.getLogger(__name__)

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
    "rainbow": """
🟥🟥🟥🟧🟧🟧🟨🟨🟨🟩🟩🟩🟦🟦🟦
🟧🟧🟧🟨🟨🟨🟩🟩🟩🟦🟦🟦🟪🟪🟪
🟨🟨🟨🟩🟩🟩🟦🟦🟦🟪🟪🟪🟥🟥🟥
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

    if len(chips) > charcodes.COLS:
        raise ValueError(
            f"{line!r} is {len(chips)} chips, wider than the board's {charcodes.COLS}"
        )
    return chips


def rows(art: str) -> list[list[str]]:
    """The artwork's rows, each padded out to the width of the widest one."""
    # Drop the newline after the opening quotes and the one before the closing
    # quotes, and nothing else: a blank top or bottom row is part of the art.
    body = art.removeprefix("\n").removesuffix("\n")
    lines = body.split("\n")
    if len(lines) > charcodes.ROWS:
        raise ValueError(
            f"artwork has {len(lines)} rows, more than the board's {charcodes.ROWS}"
        )

    rows_of_chips = [cells(line) for line in lines]
    width = max(len(chips) for chips in rows_of_chips)
    return [chips + [" "] * (width - len(chips)) for chips in rows_of_chips]


def to_grid(art: str) -> list[list[int]]:
    """Center an artwork on the board's grid of character codes."""
    chips = rows(art)
    top = (charcodes.ROWS - len(chips)) // 2
    left = (charcodes.COLS - len(chips[0])) // 2

    grid = charcodes.blank_grid()
    for row, line in enumerate(chips):
        for col, chip in enumerate(line):
            grid[top + row][left + col] = encode_chip(chip)
    return grid


#: The squares by code, for writing a grid back out. ⬛ is first in the palette,
#: so a blank chip comes back as ⬛ rather than as two spaces.
SQUARES: dict[int, str] = {code: square for square, code in PALETTE.items()}


def render_chip(code: int) -> str:
    """The two columns one character code is written as."""
    if code in SQUARES:
        return SQUARES[code]

    char = charcodes.CODE_TO_CHAR.get(code)
    if char is not None and char != " ":
        return f" {char}"

    # A black chip, or a code with no square and no character. The board shows
    # both as an unlit chip, and that is what we have to write.
    _LOGGER.warning("no square for character code %d, writing a blank chip", code)
    return "⬛"


def render(grid: list[list[int]]) -> str:
    """A grid of character codes as text, in the form ``rows`` reads back."""
    return "".join("".join(map(render_chip, row)) + "\n" for row in grid)
