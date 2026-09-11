import pytest

from vestaboard_ha import art, charcodes, rules
from vestaboard_ha.library import Library


class FakeBoard:
    def __init__(self):
        self.sent = []
        self.grids = []

    async def send_text(self, text):
        self.sent.append(text)

    async def send_characters(self, grid):
        self.grids.append(grid)


class FakeContext:
    def __init__(self, art_dir):
        self.board = FakeBoard()
        self.art = Library(art_dir)


@pytest.mark.asyncio
async def test_the_count_goes_to_the_board(tmp_path):
    ctx = FakeContext(tmp_path)

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
async def test_the_named_artwork_goes_to_the_board(tmp_path):
    ctx = FakeContext(tmp_path)

    await rules.show_art(ctx, {"name": "rainbow"})

    assert ctx.board.grids == [art.to_grid(art.ARTWORKS["rainbow"])]


@pytest.mark.asyncio
async def test_a_saved_piece_goes_to_the_board_too(tmp_path):
    ctx = FakeContext(tmp_path)
    (tmp_path / "captured.txt").write_text(art.ARTWORKS["rainbow"].strip("\n") + "\n")

    await rules.show_art(ctx, {"name": "captured"})

    assert ctx.board.grids == [art.to_grid(art.ARTWORKS["rainbow"])]


@pytest.mark.asyncio
async def test_no_name_means_any_artwork(tmp_path):
    ctx = FakeContext(tmp_path)

    await rules.show_art(ctx, {})

    [grid] = ctx.board.grids
    assert grid in [art.to_grid(piece) for piece in art.ARTWORKS.values()]
    assert len(grid) == charcodes.ROWS
