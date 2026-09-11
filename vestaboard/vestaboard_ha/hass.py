"""Minimal Home Assistant client: websocket events in, service calls out."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]

MAX_BACKOFF_SECONDS = 60.0


class HassError(RuntimeError):
    """Home Assistant refused a request."""


class HassClient:
    def __init__(
        self,
        rest_url: str,
        ws_url: str,
        token: str,
        session: aiohttp.ClientSession,
    ) -> None:
        self._rest_url = rest_url.rstrip("/")
        self._ws_url = ws_url
        self._token = token
        self._session = session
        self._message_id = 0

    @property
    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def get_state(self, entity_id: str) -> dict[str, Any] | None:
        """Current state of an entity, or None if it does not exist."""
        async with self._session.get(
            f"{self._rest_url}/states/{entity_id}", headers=self._auth_headers
        ) as response:
            if response.status == 404:
                return None
            if response.status >= 400:
                raise HassError(f"HTTP {response.status} fetching {entity_id}")
            return await response.json()

    async def call_service(
        self, domain: str, service: str, **data: Any
    ) -> list[dict[str, Any]]:
        async with self._session.post(
            f"{self._rest_url}/services/{domain}/{service}",
            headers=self._auth_headers,
            json=data,
        ) as response:
            if response.status >= 400:
                body = await response.text()
                raise HassError(
                    f"HTTP {response.status} calling {domain}.{service}: {body}"
                )
            return await response.json()

    async def listen_forever(self, handler: EventHandler, event_type: str) -> None:
        """Subscribe to an event type, reconnecting on any failure."""
        backoff = 1.0
        while True:
            try:
                await self._listen_once(handler, event_type)
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOGGER.exception(
                    "Home Assistant connection failed, retrying in %.0fs", backoff
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

    async def _listen_once(self, handler: EventHandler, event_type: str) -> None:
        async with self._session.ws_connect(self._ws_url, heartbeat=30) as ws:
            await self._authenticate(ws)

            self._message_id += 1
            await ws.send_json(
                {
                    "id": self._message_id,
                    "type": "subscribe_events",
                    "event_type": event_type,
                }
            )
            _LOGGER.info("subscribed to %s", event_type)

            async for message in ws:
                if message.type is not aiohttp.WSMsgType.TEXT:
                    continue
                payload = message.json()
                if payload.get("type") == "event":
                    await handler(payload["event"])

        raise HassError("websocket closed")

    async def _authenticate(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        greeting = await ws.receive_json()
        if greeting.get("type") != "auth_required":
            raise HassError(f"unexpected greeting: {greeting}")

        await ws.send_json({"type": "auth", "access_token": self._token})
        result = await ws.receive_json()
        if result.get("type") != "auth_ok":
            raise HassError(f"authentication failed: {result}")
        _LOGGER.info("authenticated with Home Assistant")
