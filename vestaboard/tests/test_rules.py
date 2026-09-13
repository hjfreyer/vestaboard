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
        "TODAY  3",
        "MTD 2.75",
        "YTD 2.41",
    ]


@pytest.mark.asyncio
async def test_an_average_gives_up_a_decimal_to_fit(tmp_path):
    ctx = FakeContext(tmp_path)

    # Two places would be 12.35 and 10.00, a chip wider than there is room for.
    await rules.eggs(ctx, {"today": 12, "mtd": 9.999, "ytd": 12.345})

    assert right_of_the_hen(ctx.board.grids[0])[1:] == ["MTD 10.0", "YTD 12.3"]


def chips_of(hen):
    """A hen's chips as character codes, which is what it should land as."""
    return [[art.encode_chip(chip) for chip in chips] for chips in art.rows(hen)]


def test_every_hen_is_written_out_to_the_chips_it_fills():
    for hen in rules.CHICKENS:
        chips = art.rows(hen)  # raises if the hen does not parse
        assert len(chips) == charcodes.ROWS
        # Every row to the last chip, so no hen leans on being padded out.
        assert [len(row) for row in chips] == [rules.LABEL_COL] * charcodes.ROWS


def test_every_hen_fills_the_chips_left_of_the_labels():
    for hen in rules.CHICKENS:
        grid = rules.eggs_grid({"today": 0, "mtd": 0, "ytd": 0}, hen)

        assert len(grid) == charcodes.ROWS
        assert all(len(row) == charcodes.COLS for row in grid)
        assert [row[: rules.LABEL_COL] for row in grid] == chips_of(hen)


@pytest.mark.asyncio
async def test_the_hen_is_not_always_the_same_one(tmp_path):
    ctx = FakeContext(tmp_path)

    for _ in range(40):
        await rules.eggs(ctx, {"today": 1, "mtd": 1, "ytd": 1})

    drawn = {
        tuple(tuple(row[: rules.LABEL_COL]) for row in grid)
        for grid in ctx.board.grids
    }
    assert len(drawn) > 1
    assert drawn <= {tuple(map(tuple, chips_of(hen))) for hen in rules.CHICKENS}


def test_a_hen_can_carry_a_character_among_its_squares():
    # One hen has the board's 0 for an eye, which it draws with a slash through
    # it. Squares aside, that has to survive as the character it is.
    [hen] = [hen for hen in rules.CHICKENS if " 0" in hen]

    grid = rules.eggs_grid({"today": 0, "mtd": 0, "ytd": 0}, hen)

    assert charcodes.CODE_TO_CHAR[grid[1][2]] == "0"


def test_a_hen_that_is_not_the_size_of_its_chips_is_an_error():
    one_row = "⬜" * rules.LABEL_COL
    too_wide = "\n".join([one_row + "⬜"] * charcodes.ROWS)
    too_narrow = "\n".join([one_row[:-1]] * charcodes.ROWS)
    too_short = "\n".join([one_row] * (charcodes.ROWS - 1))

    for hen in (too_wide, too_narrow, too_short):
        with pytest.raises(ValueError, match="a hen is 3 rows of 7 chips"):
            rules.eggs_grid({}, hen)


@pytest.mark.asyncio
async def test_a_missing_count_is_a_question_mark(tmp_path):
    ctx = FakeContext(tmp_path)

    await rules.eggs(ctx, {"today": 3})

    [grid] = ctx.board.grids
    assert right_of_the_hen(grid) == [
        "TODAY  3",
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
        "TODAY  3",
        "MTD 2.75",
        "YTD 2.41",
    ]


@pytest.mark.asyncio
async def test_the_values_line_up_against_the_right_edge(tmp_path):
    ctx = FakeContext(tmp_path)

    # TODAY is two chips longer than the other labels, so its value starts
    # further right -- but all three still end on the board's last chip.
    await rules.eggs(ctx, {"today": 7, "mtd": 2.75, "ytd": 12.3})

    [grid] = ctx.board.grids
    assert [row[-1] for row in grid] == [charcodes.encode_char(c) for c in "753"]


@pytest.mark.asyncio
async def test_todays_shorter_field_says_when_it_runs_out(tmp_path):
    ctx = FakeContext(tmp_path)

    # Three chips, TODAY having taken the other two, so four digits do not go.
    await rules.eggs(ctx, {"today": 1000, "mtd": 1.2, "ytd": 1.2})

    assert right_of_the_hen(ctx.board.grids[0])[0] == "TODAY99+"


def test_a_label_leaving_no_room_for_its_value_is_an_error(monkeypatch):
    monkeypatch.setattr(rules, "EGG_ROWS", (("YESTERDAY", "today", 0),))

    with pytest.raises(ValueError, match="too few"):
        rules.eggs_grid({"today": 1})


@pytest.mark.asyncio
async def test_a_count_too_big_for_four_chips_says_so(tmp_path):
    ctx = FakeContext(tmp_path)

    await rules.eggs(ctx, {"today": 1, "mtd": 1.2, "ytd": 10000})

    assert right_of_the_hen(ctx.board.grids[0])[2] == "YTD 999+"
