"""Wires rules up to Home Assistant: events in, and the device on the broker."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import aiohttp

from . import mqtt, registry, supervisor, web
from . import settings as settings_module
from .board import Vestaboard
from .device import Device, Identity
from .hass import HassClient
from .library import Library
from .settings import Broker, Settings

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Context:
    """Everything a rule needs. Passed as the first argument to every rule."""

    board: Vestaboard
    hass: HassClient
    art: Library
    settings: Settings
    device: Device


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


async def _broker(session: aiohttp.ClientSession, settings: Settings) -> Broker | None:
    """The broker to put the device on: named outright, or asked of Supervisor."""
    if settings.mqtt is not None:
        return settings.mqtt
    if settings.supervisor_token:
        return await supervisor.mqtt_broker(session, settings.supervisor_token)
    return None


async def run() -> None:
    settings = settings_module.load()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    # Importing rules is what registers them.
    from . import rules  # noqa: F401

    _LOGGER.info(
        "starting with %d channels and %d action rules%s",
        len(registry.CHANNELS),
        len(registry.ACTION_RULES),
        " (DRY RUN)" if settings.dry_run else "",
    )
    for channel in registry.CHANNELS:
        _LOGGER.info("channel %s: the %s option", channel.name, channel.label)
    for rule in registry.ACTION_RULES:
        _LOGGER.info("action %s: fire the %s event", rule.name, rule.event_type)

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=30)
    ) as session:
        identity = Identity()
        if settings.supervisor_token:
            identity = await supervisor.identity(session, settings.supervisor_token)

        device = Device(settings.state_path, identity)
        ctx = Context(
            board=Vestaboard(
                settings.api_token, session, dry_run=settings.dry_run
            ),
            hass=HassClient(
                settings.rest_url, settings.ws_url, settings.hass_token, session
            ),
            art=Library(settings.art_dir),
            settings=settings,
            device=device,
        )

        gallery = await web.serve(ctx, settings.web_port)

        try:
            await device.start(ctx)

            tasks = []
            broker = await _broker(session, settings)
            if broker is not None:
                tasks.append(mqtt.run(broker, device))
            else:
                _LOGGER.warning(
                    "no MQTT broker, so Home Assistant will not see the device; "
                    "the events still work"
                )
            if settings.has_hass:
                tasks.append(
                    ctx.hass.listen_forever(
                        lambda event: _dispatch(ctx, event), *_event_types()
                    )
                )
            else:
                _LOGGER.warning("no Home Assistant token, so no events will arrive")

            if tasks:
                await asyncio.gather(*tasks)
            else:
                # Nothing can reach the board without either, but the gallery
                # is worth staying up for.
                await asyncio.Event().wait()
        finally:
            device.stop()
            if gallery is not None:
                await gallery.cleanup()
