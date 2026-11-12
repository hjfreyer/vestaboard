"""Every HTTP request and its answer, in the log, when the level is debug.

What a rule logs about a request is what it thought worth saying, which is not
much to go on when the other end refuses for a reason of its own. This writes
down the rest: the method, the URL with its query, the headers and the body
that went out, and the status, the headers and the body that came back.

It hangs off the one ``aiohttp`` session everything shares, so it covers the
board, Home Assistant and Checkiday alike, and none of them has to know. The
judge is the exception: Anthropic's client brings a session of its own.

The keys are the one thing left out. A log gets pasted into issues and chats,
so a header that carries a secret is cut down to its last few characters --
enough to tell which key was sent, and not enough to use it.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from types import SimpleNamespace

import aiohttp

_LOGGER = logging.getLogger(__name__)

#: Parts of a header's name that mean its value is a secret.
SECRET_HINTS = ("key", "token", "auth", "cookie", "secret")

#: How much of a secret is left showing, off its end.
SHOWN = 4

#: The most of a body worth writing down. A board or a day of holidays is far
#: under it; this is for the answer that turns out to be a page of HTML.
BODY_LIMIT = 10_000


def redacted(headers: Mapping[str, str]) -> dict[str, str]:
    """The headers, with the secret ones cut down to their last few characters."""
    shown = {}
    for name, value in headers.items():
        if any(hint in name.lower() for hint in SECRET_HINTS):
            # A short value would be mostly given away by its ending.
            tail = value[-SHOWN:] if len(value) > SHOWN * 4 else ""
            value = f"<redacted>...{tail}" if tail else "<redacted>"
        shown[name] = value
    return shown


def clipped(body: str) -> str:
    """The body, or the start of it and how much more there was."""
    if len(body) <= BODY_LIMIT:
        return body
    return f"{body[:BODY_LIMIT]}... ({len(body) - BODY_LIMIT} more characters)"


async def _on_start(
    session: aiohttp.ClientSession,
    ctx: SimpleNamespace,
    params: aiohttp.TraceRequestStartParams,
) -> None:
    ctx.sent = bytearray()


async def _on_headers_sent(
    session: aiohttp.ClientSession,
    ctx: SimpleNamespace,
    params: aiohttp.TraceRequestHeadersSentParams,
) -> None:
    # The headers as they went out, rather than as they were asked for: these
    # include the ones aiohttp and the session added.
    _LOGGER.debug(
        "http: > %s %s headers=%s", params.method, params.url, redacted(params.headers)
    )


async def _on_chunk_sent(
    session: aiohttp.ClientSession,
    ctx: SimpleNamespace,
    params: aiohttp.TraceRequestChunkSentParams,
) -> None:
    ctx.sent.extend(params.chunk)


async def _on_end(
    session: aiohttp.ClientSession,
    ctx: SimpleNamespace,
    params: aiohttp.TraceRequestEndParams,
) -> None:
    if ctx.sent:
        _LOGGER.debug(
            "http: > %s %s body=%s",
            params.method,
            params.url,
            clipped(bytes(ctx.sent).decode("utf-8", "replace")),
        )

    response = params.response
    # A websocket's answer has no body to read, only a connection to keep.
    body = ""
    if response.status != 101:
        try:
            # Reading it here keeps it: whoever asked still gets the same body.
            body = clipped((await response.read()).decode("utf-8", "replace"))
        except (aiohttp.ClientError, TimeoutError) as exc:
            body = f"<unreadable: {exc!r}>"
    _LOGGER.debug(
        "http: < %s %s HTTP %d headers=%s body=%s",
        params.method,
        params.url,
        response.status,
        redacted(response.headers),
        body,
    )


async def _on_exception(
    session: aiohttp.ClientSession,
    ctx: SimpleNamespace,
    params: aiohttp.TraceRequestExceptionParams,
) -> None:
    _LOGGER.debug(
        "http: < %s %s failed: %r", params.method, params.url, params.exception
    )


def trace_configs() -> list[aiohttp.TraceConfig]:
    """What to give a session as ``trace_configs``: nothing, unless debugging.

    Decided once, when the session is made, so that a session at any other
    level is not made to read every answer twice for a log nobody keeps.
    """
    if not _LOGGER.isEnabledFor(logging.DEBUG):
        return []
    trace = aiohttp.TraceConfig()
    trace.on_request_start.append(_on_start)
    trace.on_request_headers_sent.append(_on_headers_sent)
    trace.on_request_chunk_sent.append(_on_chunk_sent)
    trace.on_request_end.append(_on_end)
    trace.on_request_exception.append(_on_exception)
    return [trace]
