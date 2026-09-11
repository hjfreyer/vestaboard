"""Vestaboard character codes.

Only needed when you want to place characters exactly; ``Vestaboard.send_text``
lets the board lay text out for you.
"""

from __future__ import annotations

BLANK = 0

CHAR_TO_CODE: dict[str, int] = {" ": BLANK}
for _i, _letter in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ", start=1):
    CHAR_TO_CODE[_letter] = _i
for _i, _digit in enumerate("1234567890", start=27):
    CHAR_TO_CODE[_digit] = _i
CHAR_TO_CODE.update(
    {
        "!": 37,
        "@": 38,
        "#": 39,
        "$": 40,
        "(": 41,
        ")": 42,
        "-": 44,
        "+": 46,
        "&": 47,
        "=": 48,
        ";": 49,
        ":": 50,
        "'": 52,
        '"': 53,
        "%": 54,
        ",": 55,
        ".": 56,
        "/": 59,
        "?": 60,
        "°": 62,
    }
)

RED = 63
ORANGE = 64
YELLOW = 65
GREEN = 66
BLUE = 67
VIOLET = 68
WHITE = 69
BLACK = 70
FILLED = 71

#: The other direction, for anything that has a grid and wants to show it.
#: Codes the board has no character for -- the colored chips -- are absent.
CODE_TO_CHAR: dict[int, str] = {code: char for char, code in CHAR_TO_CODE.items()}

#: The board's own size. This is a Vestaboard Note: 3 rows of 15 chips. A
#: flagship Vestaboard is 6 rows of 22, and the Cloud API expects whichever
#: shape the board it is pointed at has.
ROWS = 3
COLS = 15


class UnsupportedCharacter(ValueError):
    """Raised for a character the board cannot display."""


def encode_char(char: str) -> int:
    try:
        return CHAR_TO_CODE[char.upper()]
    except KeyError as exc:
        raise UnsupportedCharacter(f"Vestaboard cannot display {char!r}") from exc


def blank_grid() -> list[list[int]]:
    return [[BLANK] * COLS for _ in range(ROWS)]


def encode_lines(lines: list[str], *, center: bool = True) -> list[list[int]]:
    """Encode lines of text into a character grid, up to the board's own size."""
    if len(lines) > ROWS:
        raise ValueError(f"{len(lines)} lines does not fit in {ROWS} rows")

    grid = blank_grid()
    for row, line in enumerate(lines):
        if len(line) > COLS:
            raise ValueError(f"{line!r} is longer than {COLS} columns")
        offset = (COLS - len(line)) // 2 if center else 0
        for col, char in enumerate(line):
            grid[row][offset + col] = encode_char(char)
    return grid
