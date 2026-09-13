"""My rules. This is the file to edit; everything else is plumbing.

Each rule is an async function taking a Context, which gives you:

    ctx.board.send_text("HELLO")            # let the board lay it out
    ctx.board.send_lines(["HELLO", "YOU"])  # exact placement, 3 lines x 15 cols
    ctx.board.send_characters(ctx.art.grid())   # a piece of art, or a grid
    await ctx.hass.get_state("sensor.x")    # read Home Assistant
    await ctx.hass.call_service("light", "turn_on", entity_id="light.y")

There is one way a rule says when it runs: ``@on_action``, which runs it when
Home Assistant fires the matching ``vestaboard_*`` event. An automation is what
decides when that is -- on a clock, on an entity changing, on anything Home
Assistant can trigger on -- so changing the when is an edit in the automation
editor rather than a push to this file.
"""

from __future__ import annotations

import logging
import math
import random
from typing import Any

from . import art, charcodes
from .app import Context
from .registry import on_action

_LOGGER = logging.getLogger(__name__)


@on_action("show_art")
async def show_art(ctx: Context, data: dict[str, Any]) -> None:
    """Fire ``vestaboard_show_art`` in Home Assistant to put art on the board.

    With no ``event_data``, a random piece; with ``name: rainbow``, that one. The
    pieces are the ones in ``art.py`` and the ones captured into the gallery.
    An automation on a half-hourly time pattern is what makes it a rotation --
    see the README.
    """
    await ctx.board.send_characters(ctx.art.grid(data.get("name")))



#: The hens, filling the chips to the left of the labels. One is picked at
#: random each time the board goes up, so the eggs do not look the same every
#: morning. Each is exactly the LABEL_COL chips it has to fill, written out to
#: the last one so the source is the shape the board gets. Squares as in
#: art.py; the first hen's eye is the board's own ``0``, a character among its
#: squares, and the third's ❤ is code 62, which this board draws as a heart.
CHICKENS = (
    """
⬛⬛🟥🟥⬛⬛⬛
⬜⬜ 0⬜⬛⬛⬛
⬜⬜⬜⬜🟧⬛⬛
""",
    """
⬛⬛⬛⬛⬜⬛⬛
⬜⬛⬛⬛⬜🟨⬛
⬛⬜⬛⬜🟥⬛⬛
""",
    """
⬜⬜⬜⬜❤️🟧⬜
⬛⬛⬛⬛⬜⬜⬜
⬜⬛⬛⬛⬜⬜⬜
""",
)

#: One row per period: the label from the eighth chip, then the value against
#: the board's right edge. Today is a count of eggs and so a whole number; the
#: other two are eggs per day, which want their decimals -- two of them at
#: ``2.75``, one at ``12.3``.
EGG_ROWS = (("TODAY", "today", 0), ("MTD", "mtd", 2), ("YTD", "ytd", 2))

#: The labels all start here, under one another, so TODAY reaches two chips
#: further right than the three-letter ones do.
LABEL_COL = 7

#: Where a value starts when its label leaves room for it, which MTD and YTD
#: both do. TODAY does not, and its value starts after the label instead --
#: fewer chips, but it is the row counting a single day, so it needs fewer.
VALUE_COL = 11


def _number(raw: Any) -> float | None:
    """The value as a number, or None if the automation did not send one."""
    try:
        number = float(raw)
    except (TypeError, ValueError):
        _LOGGER.warning("eggs: %r is not a number", raw)
        return None
    if not math.isfinite(number):
        _LOGGER.warning("eggs: %r is not a number of eggs", raw)
        return None
    return number


def _value(raw: Any, places: int, width: int) -> str:
    """One value in the chips its row has, with as many decimals as fit.

    ``places`` is what the value would like; a value too big for that many
    gives them up one at a time, so a daily average reads ``2.75`` where it
    can and ``12.3`` where it cannot. Anything that is not a number at all --
    an automation that left the value out, most likely -- shows as ``?``
    rather than costing us the whole board.
    """
    number = _number(raw)
    if number is None:
        return "?"

    while places >= 0:
        text = f"{number:.{places}f}"
        if len(text) <= width:
            return text
        places -= 1

    # Better something that says it ran off the end than that many wrong digits.
    _LOGGER.warning("eggs: %.0f does not fit in %d chips", number, width)
    return "9" * (width - 1) + "+"


def eggs_grid(data: dict[str, Any], chicken: str | None = None) -> list[list[int]]:
    """The egg board: a hen on the left, a labeled count on each row.

    ``chicken`` is one of CHICKENS; None, which is what the rule passes, takes
    one of them at random.
    """
    grid = charcodes.blank_grid()

    hen = art.rows(random.choice(CHICKENS) if chicken is None else chicken)
    if (len(hen), len(hen[0])) != (charcodes.ROWS, LABEL_COL):
        raise ValueError(
            f"a hen is {charcodes.ROWS} rows of {LABEL_COL} chips, not "
            f"{len(hen)} of {len(hen[0])}"
        )

    for row, chips in enumerate(hen):
        for col, chip in enumerate(chips):
            grid[row][col] = art.encode_chip(chip)

    for row, (label, key, places) in enumerate(EGG_ROWS):
        # The value against the right edge, so the three line up under one
        # another however much of the row its own label has taken.
        start = max(VALUE_COL, LABEL_COL + len(label))
        width = charcodes.COLS - start
        if width < 2:
            raise ValueError(
                f"{label!r} leaves {width} chips for its value, which is too few"
            )

        line = label.ljust(start - LABEL_COL)
        line += _value(data.get(key), places, width).rjust(width)
        for col, char in enumerate(line):
            grid[row][LABEL_COL + col] = charcodes.encode_char(char)

    return grid


@on_action("eggs")
async def eggs(ctx: Context, data: dict[str, Any]) -> None:
    """Fire ``vestaboard_eggs`` in Home Assistant to put the egg count up.

    It takes three numbers and draws them down the right of the board against
    a hen on the left: ``today``, a count of eggs, and ``mtd`` and ``ytd``,
    eggs per day so far this month and this year::

        actions:
          - event: vestaboard_eggs
            event_data:
              today: 3
              mtd: 2.75
              ytd: 2.41

    An automation is what knows the numbers; this only lays them out.
    """
    await ctx.board.send_characters(eggs_grid(data))
