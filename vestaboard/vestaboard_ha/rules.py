"""My rules. This is the file to edit; everything else is plumbing.

Each rule is an async function taking a Context, which gives you:

    ctx.board.send_text("HELLO")            # let the board lay it out
    ctx.board.send_lines(["HELLO", "YOU"])  # exact placement, 6 lines x 22 cols
    await ctx.hass.get_state("sensor.x")    # read Home Assistant
    await ctx.hass.call_service("light", "turn_on", entity_id="light.y")

Schedules use APScheduler cron fields (hour, minute, day_of_week, ...) in the
container's timezone, which Home Assistant sets to match your own.
"""

from __future__ import annotations

from typing import Any

from .app import Context
from .registry import on_schedule, on_state


@on_schedule(hour=7, minute=0)
async def good_morning(ctx: Context) -> None:
    await ctx.board.send_text("GOOD MORNING")


@on_state("binary_sensor.front_door", to="on")
async def front_door_opened(ctx: Context, event: dict[str, Any]) -> None:
    del event  # the rule does not need the details
    await ctx.board.send_text("WELCOME HOME")


@on_state("counter.eggs")
async def eggs_changed(ctx: Context, event: dict[str, Any]) -> None:
    old = (event.get("old_state") or {}).get("state")
    new = (event.get("new_state") or {}).get("state")
    # Home Assistant also fires this event when only attributes change, and
    # once per entity on restart (old_state is None). Neither is a new count.
    if old is None or new == old or new in (None, "unknown", "unavailable"):
        return
    await ctx.board.send_text(f"EGGS: {new}")
