"""The MQTT link: one connection to the broker, kept up, with the device on it.

Home Assistant only creates a device for something it is told about, and MQTT
discovery is how a thing outside Home Assistant tells it. Everything about what
gets said is the device's business (``device.py``); this module owns the
connection and nothing else: it connects, subscribes to the topics commands
arrive on, hands the device a way to publish, and feeds it what comes in. When
the broker goes away it says so to the device, waits, and tries again.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import ssl
from collections.abc import Awaitable, Callable

import aiomqtt

from .device import AVAILABILITY_TOPIC, PREFIX, STATUS_TOPIC, Device
from .settings import Broker

_LOGGER = logging.getLogger(__name__)

#: Who we are to the broker. A second copy with the same name would knock this
#: one off, which is the right thing for a laptop standing in for the app.
CLIENT_ID = "vestaboard"

INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 60.0

Publish = Callable[..., Awaitable[None]]


def client(broker: Broker) -> aiomqtt.Client:
    """A client for the broker, with the device's last will written in."""
    return aiomqtt.Client(
        broker.host,
        broker.port,
        username=broker.username,
        password=broker.password,
        identifier=CLIENT_ID,
        # Should we die without a word, the broker says the device is gone.
        will=aiomqtt.Will(AVAILABILITY_TOPIC, "offline", retain=True),
        tls_context=ssl.create_default_context() if broker.ssl else None,
    )


async def run(broker: Broker, device: Device) -> None:
    """Keep the device on the broker, reconnecting on any failure."""
    backoff = INITIAL_BACKOFF_SECONDS
    while True:
        try:
            await serve_once(broker, device)
            _LOGGER.warning("MQTT connection closed, reconnecting in %.0fs", backoff)
        except asyncio.CancelledError:
            raise
        except aiomqtt.MqttError as exc:
            _LOGGER.warning(
                "MQTT connection failed (%s), retrying in %.0fs", exc, backoff
            )
        except Exception:
            _LOGGER.exception("MQTT link failed, retrying in %.0fs", backoff)

        await device.disconnected()
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)


async def serve_once(broker: Broker, device: Device) -> None:
    """One connection, from connect until the broker drops it."""
    async with client(broker) as link:

        async def publish(topic: str, payload: str, *, retain: bool = False) -> None:
            await link.publish(topic, payload, retain=retain)

        try:
            # Commands for any of the device's controls, and Home Assistant
            # saying it is back, which is when it wants telling about the
            # device again.
            await link.subscribe(f"{PREFIX}/+/set")
            await link.subscribe(STATUS_TOPIC)
            _LOGGER.info(
                "connected to the MQTT broker at %s:%d", broker.host, broker.port
            )
            await device.connected(publish)

            async for message in link.messages:
                payload = message.payload
                if isinstance(payload, bytes | bytearray):
                    payload = payload.decode("utf-8", errors="replace")
                await device.received(message.topic.value, str(payload))
        finally:
            # Leaving on purpose -- the app being stopped -- is a clean
            # disconnect, and the broker keeps the will for a link that broke.
            # So say it ourselves; a link that has in fact broken cannot, and
            # the will covers that.
            with contextlib.suppress(Exception):
                await asyncio.wait_for(
                    link.publish(AVAILABILITY_TOPIC, "offline", retain=True), 2
                )
