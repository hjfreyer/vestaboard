"""Wires rules up to the Home Assistant event stream."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import aiohttp

from . import registry, web
from . import settings as settings_module
from .board import Vestaboard
from .hass import HassClient
from .library import Library
from .settings import Settings

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Context:
    """Everything a rule needs. Passed as the first argument to every rule."""

    board: Vestaboard
    hass: HassClient
    art: Library
    settings: Settings


async def _dispatch(ctx: Context, event: dict[str, Any]) -> None:
    """Hand one Home Assistant event to whichever rules asked for it."""
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


def _event_types() -> list[str]:
    """Every event type the rules need, without duplicates."""
    types: list[str] = []
    for rule in registry.ACTION_RULES:
        if rule.event_type not in types:
            types.append(rule.event_type)
    return types


async def run() -> None:
    settings = settings_module.load()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    # Importing rules is what registers them.
    from . import rules  # noqa: F401

    _LOGGER.info(
        "starting with %d action rules%s",
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
            art=Library(settings.art_dir),
            settings=settings,
        )

        gallery = await web.serve(ctx, settings.web_port)

        try:
            if not settings.has_hass:
                # Nothing can reach the board without Home Assistant to ask,
                # but the gallery is worth staying up for.
                _LOGGER.warning("no Home Assistant token, serving the gallery only")
                await asyncio.Event().wait()
            else:
                await ctx.hass.listen_forever(
                    lambda event: _dispatch(ctx, event), *_event_types()
                )
        finally:
            if gallery is not None:
                await gallery.cleanup()
