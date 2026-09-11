import json

import pytest

from vestaboard_ha import charcodes
from vestaboard_ha.board import BoardError, Vestaboard


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    async def text(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    def __init__(self, status=200, body="ok"):
        self.status = status
        self.body = body
        self.calls = []

    def post(self, url, *, json=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return FakeResponse(self.status, self.body)

    def get(self, url, *, headers=None):
        self.calls.append({"url": url, "headers": headers})
        return FakeResponse(self.status, self.body)


@pytest.mark.asyncio
async def test_send_text_posts_key_and_payload():
    session = FakeSession()
    board = Vestaboard("secret", session, min_interval=0)

    await board.send_text("HELLO")

    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["json"] == {"text": "HELLO"}
    assert call["url"] == "https://cloud.vestaboard.com/"
    assert call["headers"]["X-Vestaboard-Token"] == "secret"


@pytest.mark.asyncio
async def test_send_lines_posts_a_character_grid():
    session = FakeSession()
    board = Vestaboard("secret", session, min_interval=0)

    await board.send_lines(["HI"])

    grid = session.calls[0]["json"]["characters"]
    assert len(grid) == charcodes.ROWS
    assert all(len(row) == charcodes.COLS for row in grid)


@pytest.mark.asyncio
async def test_rejects_a_grid_of_the_wrong_shape():
    board = Vestaboard("secret", FakeSession(), min_interval=0)

    with pytest.raises(ValueError):
        await board.send_characters([[0] * charcodes.COLS] * (charcodes.ROWS - 1))


@pytest.mark.asyncio
async def test_api_errors_are_raised():
    session = FakeSession(status=401, body="nope")
    board = Vestaboard("secret", session, min_interval=0)

    with pytest.raises(BoardError, match="401"):
        await board.send_text("HELLO")


@pytest.mark.asyncio
async def test_dry_run_sends_nothing():
    session = FakeSession()
    board = Vestaboard("secret", session, min_interval=0, dry_run=True)

    await board.send_text("HELLO")

    assert session.calls == []


@pytest.mark.asyncio
async def test_missing_token_is_an_error():
    board = Vestaboard("", FakeSession(), min_interval=0)

    with pytest.raises(BoardError, match="no API token"):
        await board.send_text("HELLO")


@pytest.mark.asyncio
async def test_rate_limit_delays_the_second_send(monkeypatch):
    session = FakeSession()
    board = Vestaboard("secret", session, min_interval=15)

    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr("vestaboard_ha.board.asyncio.sleep", fake_sleep)

    await board.send_text("ONE")
    await board.send_text("TWO")

    assert len(slept) == 1
    assert 14 < slept[0] <= 15
    assert len(session.calls) == 2


def a_layout(grid, *, as_string=True):
    """What the Cloud API answers a read with: JSON holding JSON."""
    layout = json.dumps(grid) if as_string else grid
    return json.dumps({"currentMessage": {"layout": layout, "id": "abc"}})


@pytest.mark.asyncio
async def test_read_returns_the_grid_the_board_is_showing():
    grid = charcodes.encode_lines(["HI"])
    session = FakeSession(body=a_layout(grid))
    board = Vestaboard("secret", session, min_interval=0)

    assert await board.read() == grid
    assert session.calls[0]["headers"]["X-Vestaboard-Token"] == "secret"


@pytest.mark.asyncio
async def test_read_takes_the_layout_as_json_or_as_a_string():
    grid = charcodes.encode_lines(["HI"])
    board = Vestaboard("secret", FakeSession(body=a_layout(grid, as_string=False)))

    assert await board.read() == grid


@pytest.mark.asyncio
async def test_read_is_not_held_back_by_dry_run():
    grid = charcodes.blank_grid()
    session = FakeSession(body=a_layout(grid))
    board = Vestaboard("secret", session, min_interval=0, dry_run=True)

    assert await board.read() == grid


@pytest.mark.asyncio
async def test_read_without_a_token_is_an_error():
    board = Vestaboard("", FakeSession(), min_interval=0)

    with pytest.raises(BoardError, match="no API token"):
        await board.read()


@pytest.mark.asyncio
async def test_read_reports_what_the_api_said():
    session = FakeSession(status=403, body="forbidden")
    board = Vestaboard("secret", session, min_interval=0)

    with pytest.raises(BoardError, match="403"):
        await board.read()


@pytest.mark.asyncio
async def test_a_reply_that_is_not_a_grid_is_an_error():
    for body in ["not json", "{}", a_layout([[0, 0], [0]]), a_layout("nonsense")]:
        board = Vestaboard("secret", FakeSession(body=body), min_interval=0)
        with pytest.raises(BoardError):
            await board.read()


@pytest.mark.asyncio
async def test_a_grid_bigger_than_the_board_is_an_error():
    too_big = [[0] * (charcodes.COLS + 1)] * charcodes.ROWS
    board = Vestaboard("secret", FakeSession(body=a_layout(too_big)), min_interval=0)

    with pytest.raises(BoardError, match="more than"):
        await board.read()
