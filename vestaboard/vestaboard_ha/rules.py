"""My rules. This is the file to edit; everything else is plumbing.

Each rule is an async function taking a Context, which gives you:

    ctx.board.send_text("HELLO")            # let the board lay it out
    ctx.board.send_lines(["HELLO", "YOU"])  # exact placement, 3 lines x 15 cols
    ctx.board.send_characters(ctx.art.grid())   # a piece of art, or a grid
    await ctx.hass.get_state("sensor.x")    # read Home Assistant
    await ctx.hass.call_service("light", "turn_on", entity_id="light.y")

A rule says when it runs: ``@on_schedule`` on a cron schedule, ``@on_state``
when an entity changes, ``@on_action`` when Home Assistant fires the matching
``vestaboard_*`` event, which is how an automation drives the board.

Schedules use APScheduler cron fields (hour, minute, day_of_week, ...) in the
container's timezone, which Home Assistant sets to match your own.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from . import art, charcodes
from .app import Context
from .registry import on_action, on_state

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


@on_state("counter.eggs")
async def eggs_changed(ctx: Context, event: dict[str, Any]) -> None:
    await ctx.board.send_text(f"EGGS: {event['new_state']['state']}")


#: The hen, in the chips to the left of the labels, flush with the board's own
#: left edge. Squares as in art.py -- a red comb, a white body, an orange beak
#: -- except for the eye, which is the board's own ``0``, drawn with a slash
#: through it.
CHICKEN = """
⬛⬛🟥🟥⬛
⬜⬜ 0⬜⬛
⬜⬜⬜⬜🟧
"""

#: One row per period: a three-chip label, a blank chip, then four chips of
#: value. Seven for the hen and 3 + 1 + 4 for the row is the board's own 15.
#: Today is a count of eggs and so a whole number; the other two are eggs per
#: day, which want their decimals -- two of them at ``2.75``, one at ``12.3``.
EGG_ROWS = (("TDY", "today", 0), ("MTD", "mtd", 2), ("YTD", "ytd", 2))
LABEL_COL = 7
VALUE_WIDTH = 4


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


def _value(raw: Any, places: int) -> str:
    """One value in the four chips it has, with as many decimals as fit.

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
        if len(text) <= VALUE_WIDTH:
            return text
        places -= 1

    # Better something that says it ran off the end than four wrong digits.
    _LOGGER.warning("eggs: %.0f does not fit in %d chips", number, VALUE_WIDTH)
    return "9" * (VALUE_WIDTH - 1) + "+"


def eggs_grid(data: dict[str, Any]) -> list[list[int]]:
    """The egg board: the hen on the left, a labeled count on each row."""
    grid = charcodes.blank_grid()

    hen = art.rows(CHICKEN)
    if len(hen[0]) > LABEL_COL:
        raise ValueError(
            f"the hen is {len(hen[0])} chips, wider than the {LABEL_COL} it has"
        )

    for row, chips in enumerate(hen):
        for col, chip in enumerate(chips):
            grid[row][col] = art.encode_chip(chip)

    for row, (label, key, places) in enumerate(EGG_ROWS):
        line = f"{label} {_value(data.get(key), places).rjust(VALUE_WIDTH)}"
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
