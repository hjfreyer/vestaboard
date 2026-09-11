import pytest

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
    assert len(grid) == 6
    assert all(len(row) == 22 for row in grid)


@pytest.mark.asyncio
async def test_rejects_a_grid_of_the_wrong_shape():
    board = Vestaboard("secret", FakeSession(), min_interval=0)

    with pytest.raises(ValueError):
        await board.send_characters([[0] * 22] * 5)


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
