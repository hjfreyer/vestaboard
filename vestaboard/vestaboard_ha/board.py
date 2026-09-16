"""Vestaboard Cloud API client."""

from __future__ import annotations

import asyncio
import json
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


def _layout(body: str) -> list[list[int]]:
    """The grid out of a current-message response."""
    try:
        layout = json.loads(body)["currentMessage"]["layout"]
        # The Cloud API sends the grid as JSON inside the JSON.
        if isinstance(layout, str):
            layout = json.loads(layout)
        grid = [[int(code) for code in row] for row in layout]
    except (KeyError, TypeError, ValueError) as exc:
        raise BoardError(f"could not make sense of {body[:200]!r}") from exc

    if not grid or any(len(row) != len(grid[0]) for row in grid):
        raise BoardError("the board sent rows of different lengths")
    if len(grid) > charcodes.ROWS or len(grid[0]) > charcodes.COLS:
        raise BoardError(
            f"the board sent {len(grid)}x{len(grid[0])} chips, more than "
            f"{charcodes.ROWS}x{charcodes.COLS}"
        )
    return grid


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

    async def read(self) -> list[list[int]]:
        """The board's current state, as a grid of character codes.

        A read changes nothing, so it is neither rate limited nor held back by
        ``dry_run``; it does still need a token.
        """
        if not self._token:
            raise BoardError("no API token configured")

        async with self._session.get(
            CLOUD_ENDPOINT, headers={"X-Vestaboard-Token": self._token}
        ) as response:
            body = await response.text()
            if response.status >= 400:
                raise BoardError(f"HTTP {response.status} from Vestaboard: {body}")

        return _layout(body)

    async def send_text(self, text: str) -> None:
        """Send text and let the board center and wrap it."""
        await self._post({"text": text})

    async def send_lines(self, lines: list[str], *, center: bool = True) -> None:
        """Send lines of text, positioned exactly as given."""
        await self.send_characters(charcodes.encode_lines(lines, center=center))

    async def send_characters(self, grid: list[list[int]]) -> None:
        """Send a grid of character codes the size of the board."""
        if len(grid) != charcodes.ROWS or any(len(r) != charcodes.COLS for r in grid):
            raise ValueError(
                f"grid must be {charcodes.ROWS}x{charcodes.COLS} character codes"
            )
        await self._post({"characters": grid})

    async def _post(self, payload: dict) -> None:
        async with self._lock:
            # Waiting is the one part of this a caller may give up on: the
            # device does, when a newer message makes the one waiting moot.
            await self._wait_for_slot()

            # From here the message is going, so the slot is spent -- before
            # the request rather than after, so that a caller cancelled in the
            # middle of it cannot let the next message out inside the interval.
            self._last_sent = time.monotonic()

            if self._dry_run:
                _LOGGER.info("DRY RUN, would send: %s", payload)
                return

            if not self._token:
                raise BoardError("no API token configured")

            # And what is going, goes. Cancelled mid-request we could not say
            # whether the board got it; so the request finishes on its own,
            # and the caller simply hears no more of it.
            sending = asyncio.ensure_future(self._send(payload))
            try:
                await asyncio.shield(sending)
            except asyncio.CancelledError:
                sending.add_done_callback(_note_if_it_failed)
                raise

    async def _send(self, payload: dict) -> None:
        async with self._session.post(
            CLOUD_ENDPOINT,
            json=payload,
            headers={"X-Vestaboard-Token": self._token},
        ) as response:
            body = await response.text()
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


def _note_if_it_failed(sending: asyncio.Future) -> None:
    """A request that outlived its caller: nobody else will hear it fail."""
    if sending.cancelled():
        return
    exc = sending.exception()
    if exc is not None:
        _LOGGER.error("a message sent without waiting failed: %s", exc)
