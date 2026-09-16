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


@on_action("text")
async def text(ctx: Context, data: dict[str, Any]) -> None:
    """Fire ``vestaboard_text`` in Home Assistant to put a message on the board.

    The message is whatever ``text`` the automation sends, and the board is
    what lays it out -- centered, wrapped over as many of the three rows as it
    needs::

        actions:
          - event: vestaboard_text
            event_data:
              text: "BACK IN AN HOUR"

    A template is the point of it: the automation works out what to say, and
    this puts it up without a push to this file.

    Anything that is not already a string is written out as one, so a number
    from a template goes up as the digits it is.
    """
    raw = data.get("text")
    message = "" if raw is None else str(raw).strip()
    if not message:
        # The Cloud API rejects a blank message, and an automation that sent
        # one meant to say something; leave the board showing what it has.
        _LOGGER.warning("text: nothing to say, %r has no text", data)
        return

    await ctx.board.send_text(message)


#: The hens, filling the chips to the left of the labels. One is picked at
#: random each time the board goes up, so the eggs do not look the same every
#: morning. Each is exactly the LABEL_COL chips it has to fill, written out to
#: the last one so the source is the shape the board gets. Squares as in
#: art.py, with characters among them where a square will not do: a ``0``, a
#: ``,``, and ❤ for code 62, which this board draws as a red heart.
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
    """
⬛⬜⬜🟥⬜⬜⬛
🟥 ,⬜🟥⬜ ,🟥
🟥⬜⬜🟨⬜⬜🟥
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


def _number(raw: Any, rule: str) -> float | None:
    """The value as a number, or None if the automation did not send one.

    ``rule`` only names the rule in the log, so that a board that came up with
    a ``?`` on it says which one was handed what.
    """
    try:
        number = float(raw)
    except (TypeError, ValueError):
        _LOGGER.warning("%s: %r is not a number", rule, raw)
        return None
    if not math.isfinite(number):
        _LOGGER.warning("%s: %r is not a finite number", rule, raw)
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
    number = _number(raw, "eggs")
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


#: The smoke, filling the chips to the left of the readings: an ember at the
#: bottom of the board with its smoke drifting up off it. There is only the
#: one, unlike the hens -- a cook puts the board up again every few minutes for
#: hours, and smoke that drew itself differently each time would make a board
#: that had not changed look like it had. Squares as in art.py, written out to
#: the last chip.
SMOKE = """
⬜⬜⬛
⬛⬜⬜
⬛⬛🟥
"""

#: What the smoke takes on the left of every row; the readings have the rest.
SMOKE_COLS = 3

#: The temperatures, in the rows they go in: the label the board shows, and the
#: key the automation sends the reading under.
SMOKER_ROWS = (("FOOD", "food"), ("AIR", "air"))

#: The countdown, which comes under the temperatures and is only there when the
#: automation sends a duration.
TIMER_LABEL = "TIMER"
TIMER_KEY = "duration"

#: What a value takes: three degrees and the F. One wanting more -- a cook with
#: over ten hours left, whose timer reads ``12:06`` -- gets it, and every row
#: shifts a chip left together, so the values stay under one another.
VALUE_WIDTH = 4

#: The most a value can take before TIMER, the longest label, would push its
#: row into the smoke.
VALUE_LIMIT = charcodes.COLS - SMOKE_COLS - len(TIMER_LABEL) - 1


def _shown(text: str, raw: Any) -> str:
    """A value if its row can hold it, and ``?`` if it runs off the end.

    Nothing about a cook is that wide, so a value that is means a sensor has
    gone wrong rather than that the meat is very hot -- and a ``?`` says as
    much, where the digits that did fit would read as a reading.
    """
    if len(text) <= VALUE_LIMIT:
        return text
    _LOGGER.warning(
        "smoker: %r needs more than the %d chips a value has", raw, VALUE_LIMIT
    )
    return "?"


def _temperature(raw: Any) -> str:
    """One temperature, as whole degrees and an F.

    The F is doing what a degree sign would: code 62 is a degree sign on the
    flagship board, but this is a Note, which draws that same flap as a red
    heart. Anything that is not a number -- a reading the automation left out,
    or a probe that is unplugged -- shows as ``?``, and the other rows still go
    up.
    """
    number = _number(raw, "smoker")
    if number is None:
        return "?"
    return _shown(f"{round(number)}F", raw)


def _minutes(raw: Any) -> int | None:
    """A duration in whole minutes, however the automation sent it.

    A number is seconds, which is what Home Assistant means by a duration and
    what one timestamp taken from another comes out as. A string with colons in
    it is ``H:MM:SS`` -- the form a timer entity's ``remaining`` takes -- or
    ``H:MM``. Seconds are dropped rather than rounded, so a timer reads the way
    a countdown does: ``2:06`` means two hours and six minutes still to go.
    """
    if isinstance(raw, str) and ":" in raw:
        hours, _, rest = raw.strip().partition(":")
        minutes, _, seconds = rest.partition(":")
        parts = [_number(part, "smoker") for part in (hours, minutes, seconds or "0")]
        if any(part is None for part in parts):
            return None
        total = parts[0] * 3600 + parts[1] * 60 + parts[2]
    else:
        total = _number(raw, "smoker")
        if total is None:
            return None

    # A cook that has run over sits at 0:00 rather than counting backwards.
    return max(0, int(total // 60))


def _countdown(raw: Any) -> str:
    """How long is left, as hours and minutes."""
    minutes = _minutes(raw)
    if minutes is None:
        return "?"
    hours, left = divmod(minutes, 60)
    return _shown(f"{hours}:{left:02d}", raw)


def smoker_grid(data: dict[str, Any]) -> list[list[int]]:
    """The smoker board: the smoke on the left, a labeled reading on each row.

    Two rows of temperature, and a third counting down when the automation
    sent a duration to count. Without one there is no TIMER row at all -- the
    ember keeps the bottom left, and the rest of that row stays dark.
    """
    grid = charcodes.blank_grid()

    smoke = art.rows(SMOKE)
    if (len(smoke), len(smoke[0])) != (charcodes.ROWS, SMOKE_COLS):
        raise ValueError(
            f"the smoke is {charcodes.ROWS} rows of {SMOKE_COLS} chips, not "
            f"{len(smoke)} of {len(smoke[0])}"
        )

    for row, chips in enumerate(smoke):
        for col, chip in enumerate(chips):
            grid[row][col] = art.encode_chip(chip)

    readings = [(label, _temperature(data.get(key))) for label, key in SMOKER_ROWS]
    duration = data.get(TIMER_KEY)
    # A template that renders to nothing while the smoker is off is an
    # automation saying there is no timer, the same as leaving the key out.
    if duration is not None and str(duration).strip():
        readings.append((TIMER_LABEL, _countdown(duration)))

    # One field for every value, as wide as the widest of them, so the readings
    # end on the board's last chip and their digits line up under one another
    # however long each row's label is.
    width = max(VALUE_WIDTH, *(len(value) for _, value in readings))
    for row, (label, value) in enumerate(readings):
        line = f"{label} {value:>{width}}"
        start = charcodes.COLS - len(line)
        if start < SMOKE_COLS:
            raise ValueError(f"{line!r} leaves no room for the smoke")
        for col, char in enumerate(line):
            grid[row][start + col] = charcodes.encode_char(char)

    return grid


@on_action("smoker")
async def smoker(ctx: Context, data: dict[str, Any]) -> None:
    """Fire ``vestaboard_smoker`` in Home Assistant to put a cook on the board.

    It takes the two temperatures worth watching -- ``food``, the probe in the
    meat, and ``air``, the smoker itself -- and optionally a ``duration``, how
    long there is left to go::

        actions:
          - event: vestaboard_smoker
            event_data:
              food: 135
              air: 227
              duration: "2:06:33"

    The duration is seconds as a number, or ``H:MM:SS`` or ``H:MM`` as a
    string, which is the form a timer entity's ``remaining`` comes in. Leave it
    out -- or send a template that renders to nothing while nothing is cooking
    -- and the board is the two temperatures, with no TIMER row.

    An automation on a time pattern is what keeps it up to date, the same way
    one puts the art up; this only lays the numbers out.
    """
    await ctx.board.send_characters(smoker_grid(data))
