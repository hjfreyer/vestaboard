"""Vestaboard Cloud API client."""

from __future__ import annotations

import asyncio
import logging
import time

import aiohttp

from . import charcodes

_LOGGER = logging.getLogger(__name__)

# The Cloud API supersedes the old Read/Write API at rw.vestaboard.com. A
# message is posted to the root path; the token comes from the Developer
# section of the Vestaboard web app.
CLOUD_ENDPOINT = "https://cloud.vestaboard.com/"

# Vestaboard throttles writes to one message every 15 seconds; anything faster
# is liable to be dropped. Keep our own floor at that limit.
MIN_INTERVAL_SECONDS = 15.0


class BoardError(RuntimeError):
    """The board rejected a message."""


class Vestaboard:
    """Posts messages, never faster than ``min_interval`` seconds apart."""

    def __init__(
        self,
        api_token: str,
        session: aiohttp.ClientSession,
        *,
        min_interval: float = MIN_INTERVAL_SECONDS,
        dry_run: bool = False,
    ) -> None:
        self._token = api_token
        self._session = session
        self._min_interval = min_interval
        self._dry_run = dry_run
        self._lock = asyncio.Lock()
        self._last_sent: float | None = None

    async def send_text(self, text: str) -> None:
        """Send text and let the board center and wrap it."""
        await self._post({"text": text})

    async def send_lines(self, lines: list[str], *, center: bool = True) -> None:
        """Send up to 6 lines, positioned exactly as given."""
        await self.send_characters(charcodes.encode_lines(lines, center=center))

    async def send_characters(self, grid: list[list[int]]) -> None:
        """Send a 6x22 grid of character codes."""
        if len(grid) != charcodes.ROWS or any(len(r) != charcodes.COLS for r in grid):
            raise ValueError(
                f"grid must be {charcodes.ROWS}x{charcodes.COLS} character codes"
            )
        await self._post({"characters": grid})

    async def _post(self, payload: dict) -> None:
        async with self._lock:
            await self._wait_for_slot()

            if self._dry_run:
                _LOGGER.info("DRY RUN, would send: %s", payload)
                self._last_sent = time.monotonic()
                return

            if not self._token:
                raise BoardError("no API token configured")

            async with self._session.post(
                CLOUD_ENDPOINT,
                json=payload,
                headers={"X-Vestaboard-Token": self._token},
            ) as response:
                body = await response.text()
                self._last_sent = time.monotonic()
                if response.status >= 400:
                    raise BoardError(f"HTTP {response.status} from Vestaboard: {body}")
                _LOGGER.debug("sent to board: %s", body)

    async def _wait_for_slot(self) -> None:
        if self._last_sent is None:
            return
        elapsed = time.monotonic() - self._last_sent
        if elapsed < self._min_interval:
            delay = self._min_interval - elapsed
            _LOGGER.debug("rate limiting, sleeping %.1fs", delay)
            await asyncio.sleep(delay)
