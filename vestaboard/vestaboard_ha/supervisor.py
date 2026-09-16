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


#: What Supervisor says, for a service, when no app is providing it.
NOT_ENABLED = "Service not enabled"


class Refused(Exception):
    """Supervisor answered, and the answer was no. Carries its message."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.message = message


async def _get(session: aiohttp.ClientSession, token: str, path: str) -> dict[str, Any]:
    """The ``data`` of a Supervisor response.

    A refusal raises ``Refused`` with what Supervisor said; not being able to
    ask at all raises ``aiohttp.ClientError``.
    """
    async with session.get(
        f"{SUPERVISOR}{path}", headers={"Authorization": f"Bearer {token}"}
    ) as response:
        try:
            body = await response.json(content_type=None)
        except ValueError as exc:
            raise Refused(response.status, f"not JSON: {exc}") from exc
        if response.status >= 400:
            message = body.get("message", body) if isinstance(body, dict) else body
            raise Refused(response.status, str(message))

    data = body.get("data") if isinstance(body, dict) else None
    return data if isinstance(data, dict) else {}


async def mqtt_broker(session: aiohttp.ClientSession, token: str) -> Broker | None:
    """The broker the Mosquitto app provides, or None if there is not one.

    Supervisor hands out the host and a login of its own for it, so an app
    that lists ``mqtt`` under ``services`` never needs the broker configured.
    With no app providing the service, Supervisor refuses the question
    rather than answering it, and that refusal is the "no broker".
    """
    try:
        data = await _get(session, token, "/services/mqtt")
    except Refused as exc:
        if exc.message == NOT_ENABLED:
            _LOGGER.info(
                "no MQTT broker: no app provides one (the Mosquitto broker app "
                "is not installed, or not running)"
            )
        else:
            _LOGGER.warning("Supervisor would not say where the MQTT broker is: %s", exc)
        return None
    except aiohttp.ClientError as exc:
        _LOGGER.warning("could not ask Supervisor for the MQTT broker: %s", exc)
        return None

    # The answer is the broker itself: host, port, a login, and which app it
    # is. There is no "available" in it; not being available is the refusal
    # above. Anything without a host is an answer we do not understand.
    if not data.get("host"):
        _LOGGER.warning(
            "Supervisor's answer for the MQTT broker has no host in it: %s",
            {key: value for key, value in data.items() if key != "password"},
        )
        return None

    provider = data.get("app") or data.get("addon")
    _LOGGER.info(
        "MQTT broker at %s:%s, provided by %s",
        data["host"],
        data.get("port") or Broker.port,
        provider or "an app Supervisor did not name",
    )
    return Broker(
        host=str(data["host"]),
        port=int(data.get("port") or Broker.port),
        username=data.get("username") or None,
        password=data.get("password") or None,
        ssl=bool(data.get("ssl", False)),
    )


async def identity(session: aiohttp.ClientSession, token: str) -> Identity:
    """The app's own version and, if it has ingress, the page it serves."""
    try:
        data = await _get(session, token, "/addons/self/info")
    except (Refused, aiohttp.ClientError) as exc:
        _LOGGER.warning("Supervisor would not say what this app is: %s", exc)
        return Identity()
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
