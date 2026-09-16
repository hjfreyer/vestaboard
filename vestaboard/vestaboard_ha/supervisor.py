"""The little of the Supervisor API the app asks for.

Supervisor is where an app finds out about the rest of the system: which MQTT
broker to use, and what it is itself called. Both come from endpoints every app
can reach with the token Supervisor gives it; the MQTT one also wants the app
to have said, in ``config.yaml``, that it uses the ``mqtt`` service.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .device import Identity
from .settings import Broker

_LOGGER = logging.getLogger(__name__)

SUPERVISOR = "http://supervisor"


async def _get(session: aiohttp.ClientSession, token: str, path: str) -> dict[str, Any]:
    """The ``data`` of a Supervisor response, or ``{}`` for anything else."""
    try:
        async with session.get(
            f"{SUPERVISOR}{path}", headers={"Authorization": f"Bearer {token}"}
        ) as response:
            body = await response.json(content_type=None)
            if response.status >= 400:
                _LOGGER.warning(
                    "Supervisor answered HTTP %d for %s: %s",
                    response.status,
                    path,
                    body.get("message", body) if isinstance(body, dict) else body,
                )
                return {}
    except (aiohttp.ClientError, ValueError) as exc:
        _LOGGER.warning("could not ask Supervisor for %s: %s", path, exc)
        return {}

    data = body.get("data") if isinstance(body, dict) else None
    return data if isinstance(data, dict) else {}


async def mqtt_broker(session: aiohttp.ClientSession, token: str) -> Broker | None:
    """The broker the Mosquitto app provides, or None if there is not one.

    Supervisor hands out the host and a login of its own for it, so an app
    that lists ``mqtt`` under ``services`` never needs the broker configured.
    """
    data = await _get(session, token, "/services/mqtt")
    if not data.get("available") or not data.get("host"):
        _LOGGER.info("no MQTT broker: the Mosquitto app is not running")
        return None

    return Broker(
        host=str(data["host"]),
        port=int(data.get("port") or Broker.port),
        username=data.get("username") or None,
        password=data.get("password") or None,
        ssl=bool(data.get("ssl", False)),
    )


async def identity(session: aiohttp.ClientSession, token: str) -> Identity:
    """The app's own version and, if it has ingress, the page it serves."""
    data = await _get(session, token, "/addons/self/info")
    slug = data.get("slug")
    url = None
    if slug and data.get("ingress"):
        # The path the frontend opens an app's ingress page at.
        url = f"homeassistant://hassio/ingress/{slug}"
    version = data.get("version")
    return Identity(
        version=str(version) if version else None,
        configuration_url=url,
    )
