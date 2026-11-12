import logging

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from vestaboard_ha import httplog

A_KEY = "abcdefghijklmnopqrstuvwxyz0123456789"


async def refuse(request):
    await request.read()
    return web.json_response(
        {"message": "You cannot consume this service"},
        status=403,
        headers={"X-RateLimit-Remaining-Day": "7"},
    )


def a_server():
    app = web.Application()
    app.router.add_route("*", "/checkiday/events", refuse)
    return TestServer(app)


def test_a_header_that_carries_a_secret_keeps_only_its_ending():
    shown = httplog.redacted(
        {
            "apikey": A_KEY,
            "X-Vestaboard-Token": A_KEY,
            "Authorization": f"Bearer {A_KEY}",
            "User-Agent": "vestaboard-ha",
        }
    )

    assert shown == {
        "apikey": "<redacted>...6789",
        "X-Vestaboard-Token": "<redacted>...6789",
        "Authorization": "<redacted>...6789",
        "User-Agent": "vestaboard-ha",
    }


def test_a_short_secret_shows_nothing_at_all():
    assert httplog.redacted({"apikey": "hunter2"}) == {"apikey": "<redacted>"}


def test_a_long_body_is_cut_short_and_says_by_how_much():
    assert httplog.clipped("a" * 10) == "a" * 10
    clipped = httplog.clipped("a" * (httplog.BODY_LIMIT + 25))
    assert clipped.endswith("... (25 more characters)")


def test_there_is_nothing_to_trace_with_unless_debugging(caplog):
    with caplog.at_level(logging.INFO, logger="vestaboard_ha.httplog"):
        assert httplog.trace_configs() == []
    with caplog.at_level(logging.DEBUG, logger="vestaboard_ha.httplog"):
        assert len(httplog.trace_configs()) == 1


@pytest.mark.asyncio
async def test_a_request_and_its_answer_are_written_down_in_full(caplog):
    with caplog.at_level(logging.DEBUG, logger="vestaboard_ha.httplog"):
        async with a_server() as server, aiohttp.ClientSession(
            trace_configs=httplog.trace_configs()
        ) as session:
            async with session.post(
                server.make_url("/checkiday/events"),
                params={"date": "2026-09-22"},
                headers={"apikey": A_KEY},
                json={"text": "hello"},
            ) as response:
                # Whoever asked still gets the body the log has already read.
                assert (await response.json())["message"].startswith("You cannot")

    said = caplog.text
    assert "> POST" in said
    assert "/checkiday/events?date=2026-09-22" in said
    assert '{"text": "hello"}' in said
    assert "< POST" in said
    assert "HTTP 403" in said
    assert "X-RateLimit-Remaining-Day" in said
    assert "You cannot consume this service" in said
    # The key is the one thing that is not.
    assert A_KEY not in said
    assert "<redacted>...6789" in said


@pytest.mark.asyncio
async def test_a_request_that_never_arrives_is_written_down_too(caplog, unused_tcp_port):
    with caplog.at_level(logging.DEBUG, logger="vestaboard_ha.httplog"):
        async with aiohttp.ClientSession(
            trace_configs=httplog.trace_configs()
        ) as session:
            with pytest.raises(aiohttp.ClientError):
                await session.get(f"http://127.0.0.1:{unused_tcp_port}/")

    assert "failed:" in caplog.text
