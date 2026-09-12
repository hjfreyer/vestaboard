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


def right_of_the_hen(grid):
    """Each row's label and count, as the text the board will show."""
    return [
        "".join(charcodes.CODE_TO_CHAR[code] for code in row[rules.LABEL_COL :])
        for row in grid
    ]


@pytest.mark.asyncio
async def test_today_is_a_count_and_the_averages_keep_their_decimals(tmp_path):
    ctx = FakeContext(tmp_path)

    await rules.eggs(ctx, {"today": 3, "mtd": 2.75, "ytd": 2.413})

    [grid] = ctx.board.grids
    assert right_of_the_hen(grid) == [
        "TDY    3",
        "MTD 2.75",
        "YTD 2.41",
    ]


@pytest.mark.asyncio
async def test_an_average_gives_up_a_decimal_to_fit(tmp_path):
    ctx = FakeContext(tmp_path)

    # Two places would be 12.35 and 10.00, a chip wider than there is room for.
    await rules.eggs(ctx, {"today": 12, "mtd": 9.999, "ytd": 12.345})

    assert right_of_the_hen(ctx.board.grids[0])[1:] == ["MTD 10.0", "YTD 12.3"]


@pytest.mark.asyncio
async def test_the_hen_has_the_seven_chips_on_the_left(tmp_path):
    ctx = FakeContext(tmp_path)

    await rules.eggs(ctx, {"today": 0, "mtd": 0, "ytd": 0})

    [grid] = ctx.board.grids
    assert len(grid) == charcodes.ROWS
    assert all(len(row) == charcodes.COLS for row in grid)
    for row, chips in enumerate(art.rows(rules.CHICKEN)):
        assert len(chips) == rules.LABEL_COL
        assert grid[row][: rules.LABEL_COL] == [art.encode_chip(c) for c in chips]


@pytest.mark.asyncio
async def test_a_missing_count_is_a_question_mark(tmp_path):
    ctx = FakeContext(tmp_path)

    await rules.eggs(ctx, {"today": 3})

    [grid] = ctx.board.grids
    assert right_of_the_hen(grid) == [
        "TDY    3",
        "MTD    ?",
        "YTD    ?",
    ]


@pytest.mark.asyncio
async def test_an_average_of_a_hundred_or_more_drops_its_decimals(tmp_path):
    ctx = FakeContext(tmp_path)

    await rules.eggs(ctx, {"today": 1, "mtd": 123.4, "ytd": 1207})

    assert right_of_the_hen(ctx.board.grids[0])[1:] == ["MTD  123", "YTD 1207"]


@pytest.mark.asyncio
async def test_counts_arriving_as_text_still_count(tmp_path):
    ctx = FakeContext(tmp_path)

    # A Home Assistant template renders to a string, not a number.
    await rules.eggs(ctx, {"today": "3", "mtd": "2.75", "ytd": "2.41"})

    [grid] = ctx.board.grids
    assert right_of_the_hen(grid) == [
        "TDY    3",
        "MTD 2.75",
        "YTD 2.41",
    ]


@pytest.mark.asyncio
async def test_a_count_too_big_for_four_chips_says_so(tmp_path):
    ctx = FakeContext(tmp_path)

    await rules.eggs(ctx, {"today": 1, "mtd": 1.2, "ytd": 10000})

    assert right_of_the_hen(ctx.board.grids[0])[2] == "YTD 999+"
