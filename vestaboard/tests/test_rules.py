import pytest

from vestaboard_ha import rules


class FakeBoard:
    def __init__(self):
        self.sent = []

    async def send_text(self, text):
        self.sent.append(text)


class FakeContext:
    def __init__(self):
        self.board = FakeBoard()


def _change(old, new):
    return {
        "entity_id": "counter.eggs",
        "old_state": None if old is None else {"state": old},
        "new_state": None if new is None else {"state": new},
    }


@pytest.mark.asyncio
async def test_a_new_count_goes_to_the_board():
    ctx = FakeContext()

    await rules.eggs_changed(ctx, _change("11", "12"))

    assert ctx.board.sent == ["EGGS: 12"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "old, new",
    [
        ("12", "12"),  # attributes changed, the count did not
        (None, "12"),  # entity seen for the first time, e.g. after a restart
        ("12", "unavailable"),
        ("12", "unknown"),
        ("12", None),  # entity removed
    ],
)
async def test_non_changes_send_nothing(old, new):
    ctx = FakeContext()

    await rules.eggs_changed(ctx, _change(old, new))

    assert ctx.board.sent == []
