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


@pytest.mark.asyncio
async def test_the_count_goes_to_the_board():
    ctx = FakeContext()

    await rules.eggs_changed(
        ctx,
        {
            "entity_id": "counter.eggs",
            "old_state": {"state": "11"},
            "new_state": {"state": "12"},
        },
    )

    assert ctx.board.sent == ["EGGS: 12"]
