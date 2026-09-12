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


#: The hen, in the seven chips on the left of every row. Squares as in art.py:
#: red comb, white head and body, orange beak, facing the numbers.
CHICKEN = """
⬛⬛⬛🟥🟥⬛⬛
⬛⬛⬜⬜⬜🟧⬛
⬛⬜⬜⬜⬜⬜⬛
"""

#: One row per period: a three-chip label, a blank chip, then four chips of
#: count. Seven for the hen and 3 + 1 + 4 for the row is the board's own 15.
EGG_ROWS = (("TDY", "today"), ("MTD", "mtd"), ("YTD", "ytd"))
LABEL_COL = 7
VALUE_WIDTH = 4


def _count(raw: Any) -> str:
    """One count, in the four chips it has to fit into.

    A count is a whole number of eggs, so anything fractional is rounded, and
    anything that is not a number at all -- an automation that left the value
    out, most likely -- shows as ``?`` rather than costing us the whole board.
    """
    try:
        number = float(raw)
    except (TypeError, ValueError):
        _LOGGER.warning("eggs: %r is not a number", raw)
        return "?"
    if not math.isfinite(number):
        _LOGGER.warning("eggs: %r is not a count", raw)
        return "?"

    text = f"{number:.0f}"
    if len(text) > VALUE_WIDTH:
        # Better something that says it ran off the end than four wrong digits.
        _LOGGER.warning("eggs: %s does not fit in %d chips", text, VALUE_WIDTH)
        return "9" * (VALUE_WIDTH - 1) + "+"
    return text


def eggs_grid(data: dict[str, Any]) -> list[list[int]]:
    """The egg board: the hen on the left, a labeled count on each row."""
    grid = charcodes.blank_grid()

    for row, chips in enumerate(art.rows(CHICKEN)):
        for col, chip in enumerate(chips):
            grid[row][col] = art.encode_chip(chip)

    for row, (label, key) in enumerate(EGG_ROWS):
        line = f"{label} {_count(data.get(key)).rjust(VALUE_WIDTH)}"
        for col, char in enumerate(line):
            grid[row][LABEL_COL + col] = charcodes.encode_char(char)

    return grid


@on_action("eggs")
async def eggs(ctx: Context, data: dict[str, Any]) -> None:
    """Fire ``vestaboard_eggs`` in Home Assistant to put the egg count up.

    It takes three numbers -- ``today``, ``mtd`` and ``ytd`` -- and draws them
    down the right of the board against a hen on the left::

        actions:
          - event: vestaboard_eggs
            event_data:
              today: 3
              mtd: 41
              ytd: 1207

    An automation is what knows the counts; this only lays them out.
    """
    await ctx.board.send_characters(eggs_grid(data))
