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
import unicodedata
from datetime import date, datetime
from typing import Any

from . import art, charcodes
from .app import Context
from .checkiday import CheckidayError
from .registry import on_action

_LOGGER = logging.getLogger(__name__)


@on_action("show_art")
async def show_art(ctx: Context, data: dict[str, Any]) -> None:
    """Fire ``vestaboard_show_art`` in Home Assistant to put art on the board.

    With no ``event_data``, a random piece from the ``art`` category; with
    ``category: bedtime``, a random one from that category instead; with
    ``name: rainbow``, that piece whichever category it is in. The pieces are
    the ones in ``art.py`` and the ones captured into the gallery. An automation
    on a half-hourly time pattern is what makes it a rotation -- and a second
    one, firing at bedtime with the category, is what makes the board quiet down
    at night. See the README.
    """
    await ctx.board.send_characters(
        ctx.art.grid(data.get("name"), data.get("category"))
    )


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

#: Home Assistant's weather entities all report one of these fifteen
#: conditions, whichever service the forecast came from, so this is the whole
#: list there is to draw. Each is the ICON_COLS chips that go in the middle of
#: the forecast board, written out to the last one, in the squares art.py uses.
#: A cloud is the same pyramid wherever it appears, and what falls out of it is
#: written as characters -- rain as colons, a downpour as slashes, snow as
#: hashes, hail as its stones -- which read as falling where a chip under a
#: cloud reads as more cloud. Some of it cannot be told apart at four chips
#: across -- a gust from a variant gust, a clear day from a clear night -- and
#: those are drawn alike on purpose; the board is saying take a coat, not
#: reading out the METAR.
CONDITIONS: dict[str, str] = {
    "sunny": """
🟨🟨🟨🟨
🟨🟨🟨🟨
🟨🟨🟨🟨
""",
    "clear-night": """
🟨🟨🟨🟨
🟨🟨🟨🟨
🟨🟨🟨🟨
""",
    "partlycloudy": """
🟨🟨🟨⬛
🟨⬜⬜⬛
⬜⬜⬜⬜
""",
    "cloudy": """
⬛⬜⬜⬛
⬜⬜⬜⬜
⬛⬛⬛⬛
""",
    "fog": """
⬜⬜⬜⬜
⬛⬛⬛⬛
⬜⬜⬜⬜
""",
    "windy": """
⬜⬜⬜⬛
⬛⬛⬛⬛
⬛⬜⬜⬜
""",
    "windy-variant": """
⬜⬜⬜⬛
⬛⬛⬛⬛
⬛⬜⬜⬜
""",
    "rainy": """
⬛⬜⬜⬛
⬜⬜⬜⬜
 :⬛ :⬛
""",
    "pouring": """
⬛⬜⬜⬛
⬜⬜⬜⬜
 / / / /
""",
    "lightning": """
⬛⬜⬜⬛
⬜⬜🟨⬜
⬛🟨⬛⬛
""",
    "lightning-rainy": """
⬛⬜⬜⬛
⬜⬜🟨⬜
 :🟨⬛ :
""",
    "snowy": """
⬛⬜⬜⬛
⬜⬜⬜⬜
 #⬛ #⬛
""",
    "snowy-rainy": """
⬛⬜⬜⬛
⬜⬜⬜⬜
 :⬛ #⬛
""",
    "hail": """
⬛⬜⬜⬛
⬜⬜⬜⬜
 O⬛ O⬛
""",
    "exceptional": """
⬛🟥🟥⬛
⬛🟥🟥⬛
⬛🟥🟥⬛
""",
}

#: What goes in the middle when the automation sent a condition we have never
#: heard of, or none at all. A board that says it does not know beats a board
#: that quietly draws sunshine.
UNKNOWN_CONDITION = """
⬛⬛⬛⬛
⬛ ?⬛⬛
⬛⬛⬛⬛
"""

#: The three columns of the forecast board: the date on the left, the condition
#: drawn in the middle, and the temperatures against the right edge. The date
#: is three chips, since a weekday and a month are three letters and a day of
#: the month two digits, and the condition four. The temperatures take what
#: they need of the rest, and the condition sits in the middle of what is left.
DATE_COL = 0
DATE_COLS = 3
ICON_COLS = 4

#: What a column of temperatures takes: as many chips as its widest reading.
#: Never fewer than two, so that a 9C morning and a 10C one put the board up
#: the same way, and never more than three, which is a 100F afternoon and a
#: -20C morning both.
MIN_TEMP_WIDTH = 2
MAX_TEMP_WIDTH = 3


def _either(data: dict[str, Any], *keys: str) -> Any:
    """The first of these keys the automation said anything under.

    Each thing the forecast board wants has two names: ours, and the one a
    Home Assistant forecast entry already calls it. That is what lets an
    automation hand the entry over whole rather than picking it apart.
    """
    for key in keys:
        value = data.get(key)
        if value is not None and str(value).strip():
            return value
    return None


def _date_asked_for(
    raw: Any, today: date | None = None, *, rule: str = "forecast"
) -> date:
    """The day the board is for: what the automation sent, or our own clock.

    A date sent as ``{{ now().date() }}`` or a forecast's own ``datetime`` is
    the automation being authoritative about the timezone, which it knows
    better than we do; with nothing sent we use the clock in the container,
    which Supervisor sets to the same timezone as Home Assistant.

    ``rule`` only names the rule in the log, since more than one of them wants
    a day and a board that came up for the wrong one should say which asked.
    """
    if raw is not None and str(raw).strip():
        try:
            return datetime.fromisoformat(str(raw).strip()).date()
        except ValueError:
            _LOGGER.warning("%s: %r is not a date, using today", rule, raw)
    return today or date.today()


def _date_lines(when: date) -> list[str]:
    """The date down the left: the weekday, the month, and the day of it."""
    return [
        when.strftime("%a").upper(),
        when.strftime("%b").upper(),
        str(when.day),
    ]


#: What an automation can call the two units a weather entity reports in. The
#: spellings with the degree sign are what the entity's own ``temperature_unit``
#: attribute says, so that can be sent straight through.
UNITS: dict[str, str] = {
    "C": "C",
    "°C": "C",
    "CELSIUS": "C",
    "F": "F",
    "°F": "F",
    "FAHRENHEIT": "F",
}

#: What the temperatures are in when the automation does not say. Home
#: Assistant hands a forecast over in whatever unit it is set to, which is
#: Celsius unless that is US customary.
DEFAULT_UNIT = "C"


def _unit(raw: Any) -> str:
    """Which unit the automation's temperatures are in.

    A weather entity is only ever set to one of the two, so anything else is an
    automation sending something that is not a unit at all; that is worth
    saying, and Celsius is the better guess to carry on with.
    """
    said = ("" if raw is None else str(raw)).strip().upper()
    if not said:
        return DEFAULT_UNIT
    unit = UNITS.get(said)
    if unit is None:
        _LOGGER.warning("forecast: %r is not a unit, reading it as Celsius", raw)
        return DEFAULT_UNIT
    return unit


def _degrees(value: float) -> str:
    """One temperature in the chips it has, or ``?`` if it runs off the end.

    Nothing a forecast says is four chips wide, so a value that is means the
    automation sent something that is not a temperature.
    """
    text = str(round(value))
    if len(text) <= MAX_TEMP_WIDTH:
        return text
    _LOGGER.warning("forecast: %s needs more than %d chips", text, MAX_TEMP_WIDTH)
    return "?"


def _both(reading: Any, unit: str) -> tuple[str, str]:
    """One reading in Fahrenheit and in Celsius, whichever it arrived as.

    The automation sends the reading in whichever unit its Home Assistant hands
    forecasts out in, and the other one is ours to work out. A reading that is
    missing or is not a number is ``?`` in both, rather than costing us the
    board.
    """
    number = _number(reading, "forecast")
    if number is None:
        return "?", "?"
    if unit == "F":
        return _degrees(number), _degrees((number - 32) * 5 / 9)
    return _degrees(number * 9 / 5 + 32), _degrees(number)


def temperatures(data: dict[str, Any]) -> tuple[str, ...]:
    """The right-hand column: the high, the low, and which column is which.

    Each column is as wide as the widest reading in it, so a board whose
    Celsius is two digits -- which is most of them -- does not hold a third
    chip back against the days it is three. The middle of the board gets it
    instead, and the columns still line up under one another and under their
    own letter.
    """
    unit = _unit(_either(data, "unit", "temperature_unit"))
    high = _both(_either(data, "high", "temperature"), unit)
    low = _both(_either(data, "low", "templow"), unit)

    warm, cool = (
        max(MIN_TEMP_WIDTH, len(high[side]), len(low[side])) for side in (0, 1)
    )
    return tuple(
        f"{fahrenheit:>{warm}} {celsius:>{cool}}"
        for fahrenheit, celsius in (high, low, ("F", "C"))
    )


def condition_col(width: int) -> int:
    """Where the condition is drawn: the middle of what the temperatures left.

    ``width`` is how many chips they took, so a board whose readings are short
    draws the weather further from the date than one whose readings are long.
    """
    room = charcodes.COLS - width - (DATE_COL + DATE_COLS)
    if room < ICON_COLS:
        raise ValueError(
            f"{room} chips between the date and the temperatures is too few "
            f"for a condition, which takes {ICON_COLS}"
        )
    return DATE_COL + DATE_COLS + (room - ICON_COLS) // 2


def forecast_grid(data: dict[str, Any], today: date | None = None) -> list[list[int]]:
    """The forecast board: the date, the day's weather, and its temperatures.

    ``today`` is only there for the tests; the rule lets ``_date_asked_for``
    work out the day.
    """
    grid = charcodes.blank_grid()

    when = _date_asked_for(_either(data, "date", "datetime"), today)
    for row, line in enumerate(_date_lines(when)):
        for col, char in enumerate(line):
            grid[row][DATE_COL + col] = charcodes.encode_char(char)

    condition = str(data.get("condition", "")).strip().lower()
    icon = CONDITIONS.get(condition)
    if icon is None:
        _LOGGER.warning("forecast: %r is not a forecast I can draw", condition)
        icon = UNKNOWN_CONDITION

    chips = art.rows(icon)
    if (len(chips), len(chips[0])) != (charcodes.ROWS, ICON_COLS):
        raise ValueError(
            f"a condition is {charcodes.ROWS} rows of {ICON_COLS} chips, not "
            f"{len(chips)} of {len(chips[0])}"
        )

    # The high, the low, and which column is which, so the two numbers on a row
    # are one temperature said twice rather than two temperatures. They end on
    # the board's last chip, and what they did not need is the middle's.
    readings = temperatures(data)
    start = charcodes.COLS - len(readings[0])
    for row, line in enumerate(readings):
        for col, char in enumerate(line):
            grid[row][start + col] = charcodes.encode_char(char)

    icon_col = condition_col(len(readings[0]))
    for row, line in enumerate(chips):
        for col, chip in enumerate(line):
            grid[row][icon_col + col] = art.encode_chip(chip)

    return grid


@on_action("forecast")
async def forecast(ctx: Context, data: dict[str, Any]) -> None:
    """Fire ``vestaboard_forecast`` to put the day and its weather up.

    It takes the day's forecast -- ``condition``, and ``high`` and ``low``,
    which a daily forecast calls ``temperature`` and ``templow``::

        actions:
          - action: weather.get_forecasts
            target:
              entity_id: weather.home
            data:
              type: daily
            response_variable: forecasts
          - event: vestaboard_forecast
            event_data:
              condition: "{{ forecasts['weather.home'].forecast[0].condition }}"
              high: "{{ forecasts['weather.home'].forecast[0].temperature }}"
              low: "{{ forecasts['weather.home'].forecast[0].templow }}"

    Those are the names a daily forecast entry already uses, so the three
    fields can be copied off one under either name.

    The temperatures are read as Celsius unless the automation says otherwise,
    since that is what a forecast comes in unless Home Assistant is set to US
    customary units. A Home Assistant that is says so, and the weather entity
    knows its own answer::

        actions:
          - event: vestaboard_forecast
            event_data:
              unit: "{{ state_attr('weather.home', 'temperature_unit') }}"
              ...

    Whichever comes in, both columns go up: the other one is worked out here.

    The board is the date down the left, the forecast drawn in the middle, and
    the high over the low on the right, each in Fahrenheit and Celsius. The
    date is ours unless the automation sends one -- as ``date``, or as the
    ``datetime`` a forecast entry carries.
    """
    await ctx.board.send_characters(forecast_grid(data))


#: What an automation sends to make us ask Checkiday about a day all over
#: again. A day is written down the first time we ask, and that is what stops
#: an automation on a time pattern from spending the month's requests before
#: lunchtime; this is the way to say that today has changed its mind.
REFRESH_KEY = "refresh"

#: How many times a day is asked about before it is left until tomorrow. A
#: failed ask spends one of the key's monthly allowance the same as a good one,
#: and the free allowance is a hundred, so an automation on a time pattern and
#: an API having a bad morning could between them spend the month by lunchtime.
#: Three is enough to ride out a blip and few enough to notice in the log.
MAX_ATTEMPTS = 3


def _flag(raw: Any) -> bool:
    """A yes or a no from an automation, which may have templated it to a string.

    Home Assistant renders a template to text before we ever see it, so a
    ``true`` that started life as a boolean arrives as the word.
    """
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


@on_action("fetch_holidays")
async def fetch_holidays(ctx: Context, data: dict[str, Any]) -> None:
    """Fire ``vestaboard_fetch_holidays`` to find out what today is a holiday for.

    Checkiday knows several thousand of them, and this asks which fall today::

        alias: Vestaboard holidays
        triggers:
          - trigger: time
            at: "06:30:00"
        actions:
          - event: vestaboard_fetch_holidays

    Nothing reaches the board: this is the fetching, and the names it writes
    down are what a board is made out of later. What it writes is two caches
    under the app's own storage -- a file per day holding that date's holiday
    ids, and a file per holiday saying what an id means -- which is why a
    holiday's name is only ever asked for once however often it comes round.

    A day that is already written down is not fetched again, since every ask
    is one of a monthly allowance, so firing this twice in a day costs nothing
    and an automation is free to fire it on a time pattern. To go back and ask
    anyway -- a holiday added to Checkiday during the day, most likely::

        actions:
          - event: vestaboard_fetch_holidays
            event_data:
              refresh: true

    Which day this is about is Checkiday's to say rather than ours. Asking for
    a particular date wants a Pro plan, so nothing is asked for and today is
    what comes back -- worked out in Checkiday's own timezone unless the plan
    is an Enterprise one, which is why the day is taken from the answer. Our
    own is only a guess at which day that will be, which is all the cache
    check needs; they agree every hour of the day but the last few.
    """
    # Our own today, which is a guess at Checkiday's: good enough to know
    # whether we have already asked, and replaced by the answer's own day.
    today = date.today()
    anyway = _flag(data.get(REFRESH_KEY))

    known = ctx.holidays.ids_for(today)
    if known is not None and not anyway:
        _LOGGER.info(
            "holidays: %s is already fetched, with %d on it; not asking again",
            today,
            len(known),
        )
        return

    if not ctx.checkiday.configured:
        # Worth a word rather than an exception: an app with no key in its
        # configuration is one this feature was never set up on.
        _LOGGER.warning(
            "holidays: no Checkiday API key configured, so there is nothing "
            "to fetch for %s",
            today,
        )
        return

    attempts = ctx.holidays.attempts_for(today)
    if attempts >= MAX_ATTEMPTS and not anyway:
        _LOGGER.warning(
            "holidays: asking about %s has gone wrong %d times, so it is being "
            "left until tomorrow; fire this with refresh: true to try anyway",
            today,
            attempts,
        )
        return

    try:
        listing = await ctx.checkiday.holidays()
    except CheckidayError:
        # A request spent for nothing. Worth writing down, since it is the
        # count of them that stops us spending the rest of the month too.
        ctx.holidays.note_attempt(today)
        raise

    day = listing.day or today
    if day != today:
        # The evening hours when Checkiday's timezone has turned over and ours
        # has not. Their day is the one the holidays are actually for.
        _LOGGER.info(
            "holidays: Checkiday answered for %s where our own today is %s; "
            "filing them under theirs",
            day,
            today,
        )

    ctx.holidays.remember(day, listing.holidays)
    _LOGGER.info(
        "holidays: %s is %s",
        day,
        ", ".join(holiday.name for holiday in listing.holidays)
        or "no holiday at all",
    )


#: The words a holiday uses to say how far its claim reaches. They are the
#: first thing to go when a name will not fit: written the short way where
#: there is one, and dropped after that. A board on a kitchen wall is not in
#: any doubt about which world it is on.
SCOPE_WORDS = ("NATIONAL", "INTERNATIONAL", "WORLD")

#: How to write one of them shorter. WORLD is already as short as it goes, so
#: it has no entry here and survives to the step that drops it instead.
SCOPE_SHORT = {"NATIONAL": "NAT'L", "INTERNATIONAL": "INT'L"}

#: What stands in for the words that did not make it. The board has no single
#: flap for one, so it is three full stops and takes three chips.
ELLIPSIS = "..."

#: Spellings the board has no flap for, and what to write instead. Checkiday
#: writes for a web page -- curly quotes, en dashes, the odd accent -- and the
#: board has none of that.
SUBSTITUTIONS = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‛": "'",
        "`": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        "―": "-",
        "…": ELLIPSIS,
    }
)


def sayable(name: str) -> str:
    """A holiday's name in the letters this board actually has.

    The plain spelling of anything fancy, accents taken off the letters they
    sit on, and then a space for whatever is still unsayable -- one strange
    character in a name should cost that character and not the whole board.
    """
    said = name.translate(SUBSTITUTIONS)
    # An accent comes apart into a letter and a mark of its own, and it is the
    # mark that goes: CAFÉ is a word the board can say, once the É is an E.
    said = unicodedata.normalize("NFKD", said)
    said = "".join(mark for mark in said if not unicodedata.combining(mark))
    return "".join(
        char if char in charcodes.CHAR_TO_CODE else " " for char in said.upper()
    )


def _lines(words: list[str]) -> list[str] | None:
    """The words wrapped onto the board, or None if they will not go.

    At the spaces and nowhere else: the board has no hyphen worth the name, and
    a word broken over two rows reads as two words.
    """
    lines: list[str] = []
    line = ""
    for word in words:
        if len(word) > charcodes.COLS:
            return None
        nxt = f"{line} {word}" if line else word
        if len(nxt) <= charcodes.COLS:
            line = nxt
            continue
        lines.append(line)
        line = word
        if len(lines) == charcodes.ROWS:
            # A row's worth of words still in hand and no row left to put it on.
            return None
    if line:
        lines.append(line)
    return lines or None


def _shortened(words: list[str]) -> list[str]:
    """The scope written the short way, where there is a short way."""
    return [SCOPE_SHORT.get(word, word) for word in words]


def _unscoped(words: list[str]) -> list[str]:
    """The scope gone altogether.

    A holiday whose name is nothing but its scope keeps it, since a board with
    nothing on it is worse than one that overreaches.
    """
    return [word for word in words if word not in SCOPE_WORDS] or words


def _ellipsized(words: list[str]) -> list[str]:
    """As many words as go on, and dots for the ones that did not."""
    for count in range(len(words) - 1, 0, -1):
        lines = _lines([*words[: count - 1], words[count - 1] + ELLIPSIS])
        if lines is not None:
            return lines

    # One word, and even that is too long for a row: cut the word itself.
    room = charcodes.COLS - len(ELLIPSIS)
    return [words[0][:room] + ELLIPSIS]


def holiday_lines(name: str) -> list[str]:
    """One holiday's name laid out on the board, shortened until it goes on.

    Four goes at it, each giving up a little more than the last: the name as it
    is, then the scope written short, then the scope dropped, and then dots for
    whatever is left over. Most of a long holiday's name is its scope, so it is
    rare to get past the third.

    The scope is dropped from the name as it was written rather than from the
    shortened one, since ``NAT'L`` is no longer the word being looked for.
    """
    words = sayable(name).split()
    if not words:
        raise ValueError(f"{name!r} has nothing in it the board can show")

    for attempt in (words, _shortened(words), _unscoped(words)):
        lines = _lines(attempt)
        if lines is not None:
            return lines
    return _ellipsized(_unscoped(words))


def _down_the_middle(lines: list[str]) -> list[str]:
    """The lines in the middle of the board rather than up against the top.

    ``encode_lines`` centers a line across its row but starts at the first one,
    so a one-line holiday would otherwise sit on the top row with two empty
    rows under it.
    """
    return ["" for _ in range((charcodes.ROWS - len(lines)) // 2)] + lines


@on_action("show_holiday")
async def show_holiday(ctx: Context, data: dict[str, Any]) -> None:
    """Fire ``vestaboard_show_holiday`` to put one of today's holidays up.

    It reads what ``vestaboard_fetch_holidays`` wrote down, picks one of the
    day's holidays at random, and puts its name on the board::

        alias: Vestaboard holiday
        triggers:
          - trigger: time_pattern
            hours: "/2"
        actions:
          - event: vestaboard_show_holiday

    Nothing is asked of Checkiday here, so this is free to fire as often as you
    like -- it only ever reads the day the fetch already paid for. A day that
    has not been fetched, or that turned out to hold no holidays, is logged and
    leaves the board showing whatever it had.

    The day is today unless the automation sends a ``date``, which is mostly a
    way to look at a day that has already been.
    """
    day = _date_asked_for(_either(data, "date", "datetime"), rule="holidays")

    # A name with nothing sayable in it should cost us that holiday rather
    # than the turn: the board is better off with one of the others on it.
    showable = []
    for holiday in ctx.holidays.holidays_for(day):
        if sayable(holiday.name).split():
            showable.append(holiday)
        else:
            _LOGGER.warning(
                "holidays: leaving %r out, the board cannot say any of it",
                holiday.name,
            )

    if not showable:
        _LOGGER.warning(
            "holidays: nothing written down for %s that the board can show; "
            "has vestaboard_fetch_holidays run?",
            day,
        )
        return

    holiday = random.choice(showable)
    lines = holiday_lines(holiday.name)
    _LOGGER.info("holidays: showing %r as %s", holiday.name, lines)
    await ctx.board.send_lines(_down_the_middle(lines))
