"""My rules. This is the file to edit; everything else is plumbing.

Each rule is an async function taking a Context, which gives you:

    ctx.board.send_text("HELLO")            # let the board lay it out
    ctx.board.send_lines(["HELLO", "YOU"])  # exact placement, 6 lines x 22 cols
    ctx.board.send_characters(art.grid())   # a grid of character codes
    await ctx.hass.get_state("sensor.x")    # read Home Assistant
    await ctx.hass.call_service("light", "turn_on", entity_id="light.y")

A rule says when it runs: ``@on_schedule`` on a cron schedule, ``@on_state``
when an entity changes, ``@on_action`` when Home Assistant fires the matching
``vestaboard_*`` event, which is how an automation drives the board.

Schedules use APScheduler cron fields (hour, minute, day_of_week, ...) in the
container's timezone, which Home Assistant sets to match your own.
"""

from __future__ import annotations

from typing import Any

from . import art
from .app import Context
from .registry import on_action, on_state


@on_action("show_art")
async def show_art(ctx: Context, data: dict[str, Any]) -> None:
    """Fire ``vestaboard_show_art`` in Home Assistant to put art on the board.

    With no ``event_data``, a random piece from ``art.py``; with
    ``name: heart``, that one. An automation on a half-hourly time pattern is
    what makes it a rotation -- see the README.
    """
    await ctx.board.send_characters(art.grid(data.get("name")))


@on_state("counter.eggs")
async def eggs_changed(ctx: Context, event: dict[str, Any]) -> None:
    await ctx.board.send_text(f"EGGS: {event['new_state']['state']}")
