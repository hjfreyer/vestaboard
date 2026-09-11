import pytest

from vestaboard_ha import art, charcodes, rules


class FakeBoard:
    def __init__(self):
        self.sent = []
        self.grids = []

    async def send_text(self, text):
        self.sent.append(text)

    async def send_characters(self, grid):
        self.grids.append(grid)


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


@pytest.mark.asyncio
async def test_the_named_artwork_goes_to_the_board():
    ctx = FakeContext()

    await rules.show_art(ctx, {"name": "invader"})

    assert ctx.board.grids == [art.to_grid(art.ARTWORKS["invader"])]


@pytest.mark.asyncio
async def test_no_name_means_any_artwork():
    ctx = FakeContext()

    await rules.show_art(ctx, {})

    [grid] = ctx.board.grids
    assert grid in [art.to_grid(piece) for piece in art.ARTWORKS.values()]
    assert len(grid) == charcodes.ROWS
