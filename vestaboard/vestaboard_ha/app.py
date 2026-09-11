"""Wires rules up to the scheduler and the Home Assistant event stream."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from . import registry
from . import settings as settings_module
from .board import Vestaboard
from .hass import HassClient
from .settings import Settings

_LOGGER = logging.getLogger(__name__)

STATE_CHANGED = "state_changed"


@dataclass(frozen=True)
class Context:
    """Everything a rule needs. Passed as the first argument to every rule."""

    board: Vestaboard
    hass: HassClient
    settings: Settings


async def _dispatch(ctx: Context, event: dict[str, Any]) -> None:
    """Hand one Home Assistant event to whichever rules asked for it."""
    if event.get("event_type") == STATE_CHANGED:
        await _dispatch_state_change(ctx, event)
    else:
        await _dispatch_action(ctx, event)


async def _dispatch_action(ctx: Context, event: dict[str, Any]) -> None:
    event_type = event.get("event_type")
    data = event.get("data", {})
    for rule in registry.ACTION_RULES:
        if rule.event_type != event_type:
            continue
        _LOGGER.info("rule %s triggered by %s", rule.name, event_type)
        try:
            await rule.fn(ctx, data)
        except Exception:
            _LOGGER.exception("rule %s failed", rule.name)


async def _dispatch_state_change(ctx: Context, event: dict[str, Any]) -> None:
    data = event.get("data", {})
    for rule in registry.STATE_RULES:
        if not rule.matches(data):
            continue
        _LOGGER.info("rule %s triggered by %s", rule.name, data.get("entity_id"))
        try:
            await rule.fn(ctx, data)
        except Exception:
            _LOGGER.exception("rule %s failed", rule.name)


async def _run_scheduled(ctx: Context, rule: registry.ScheduledRule) -> None:
    _LOGGER.info("rule %s triggered by schedule", rule.name)
    try:
        await rule.fn(ctx)
    except Exception:
        _LOGGER.exception("rule %s failed", rule.name)


def _event_types() -> list[str]:
    """Every event type the rules need, without duplicates."""
    types = [STATE_CHANGED] if registry.STATE_RULES else []
    for rule in registry.ACTION_RULES:
        if rule.event_type not in types:
            types.append(rule.event_type)
    return types


def _build_scheduler(ctx: Context) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    for rule in registry.SCHEDULED_RULES:
        scheduler.add_job(
            _run_scheduled,
            trigger=CronTrigger(**rule.cron),
            args=[ctx, rule],
            id=rule.name,
            name=rule.name,
            misfire_grace_time=300,
            coalesce=True,
        )
    return scheduler


async def run() -> None:
    settings = settings_module.load()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    # Importing rules is what registers them.
    from . import rules  # noqa: F401

    _LOGGER.info(
        "starting with %d scheduled, %d state and %d action rules%s",
        len(registry.SCHEDULED_RULES),
        len(registry.STATE_RULES),
        len(registry.ACTION_RULES),
        " (DRY RUN)" if settings.dry_run else "",
    )
    for rule in registry.ACTION_RULES:
        _LOGGER.info("action %s: fire the %s event", rule.name, rule.event_type)

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=30)
    ) as session:
        ctx = Context(
            board=Vestaboard(
                settings.api_token, session, dry_run=settings.dry_run
            ),
            hass=HassClient(
                settings.rest_url, settings.ws_url, settings.hass_token, session
            ),
            settings=settings,
        )

        scheduler = _build_scheduler(ctx)
        scheduler.start()

        try:
            if not settings.has_hass:
                _LOGGER.warning(
                    "no Home Assistant token, running scheduled rules only"
                )
                await asyncio.Event().wait()
            else:
                await ctx.hass.listen_forever(
                    lambda event: _dispatch(ctx, event), *_event_types()
                )
        finally:
            scheduler.shutdown(wait=False)
