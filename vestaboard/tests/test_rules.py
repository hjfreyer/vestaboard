import asyncio

import pytest
import pytest_asyncio

from vestaboard_ha import art, charcodes, rules
from vestaboard_ha.device import Device
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
        self.device = Device(art_dir / "device.json")


@pytest_asyncio.fixture
async def ctx(tmp_path):
    """A context on a fresh device, which holds -- so starting draws nothing."""
    ctx = FakeContext(tmp_path)
    await ctx.device.start(ctx)
    yield ctx
    ctx.device.stop()


# -- the art ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_named_artwork_goes_to_the_board(ctx):
    await rules.show_art(ctx, {"name": "rainbow"})

    assert ctx.board.grids == [art.to_grid(art.ARTWORKS["rainbow"])]


@pytest.mark.asyncio
async def test_naming_a_piece_tunes_to_art_and_holds_that_piece(ctx):
    await rules.show_art(ctx, {"name": "rainbow"})

    assert ctx.device.channel == "art"
    assert ctx.device.piece == "rainbow"
    assert ctx.device.showing == "Art: rainbow"


@pytest.mark.asyncio
async def test_a_saved_piece_goes_to_the_board_too(tmp_path, ctx):
    (tmp_path / "captured.txt").write_text(art.ARTWORKS["rainbow"].strip("\n") + "\n")

    await rules.show_art(ctx, {"name": "captured"})

    assert ctx.board.grids == [art.to_grid(art.ARTWORKS["rainbow"])]


@pytest.mark.asyncio
async def test_no_name_means_any_artwork(ctx):
    await rules.show_art(ctx, {})

    [grid] = ctx.board.grids
    assert grid in [art.to_grid(piece) for piece in art.ARTWORKS.values()]
    assert len(grid) == charcodes.ROWS
    # And the Piece select goes back to Random, whatever it said before.
    assert ctx.device.piece is None


@pytest.mark.asyncio
async def test_a_piece_that_does_not_exist_leaves_the_board_alone(ctx):
    with pytest.raises(ValueError, match="no piece named 'nonesuch'"):
        await rules.show_art(ctx, {"name": "nonesuch"})

    assert ctx.board.grids == []
    assert ctx.device.channel == "hold"


@pytest.mark.asyncio
async def test_a_random_piece_asks_to_be_changed_after_the_rotation(ctx):
    await ctx.device.adjust(rotation=45)

    await rules.show_art(ctx, {})

    # Not an assertion on the clock: that the redraw is waiting is enough.
    assert ctx.device._redraw is not None
    assert not ctx.device._redraw.done()


@pytest.mark.asyncio
async def test_a_named_piece_stays_up(ctx):
    await ctx.device.adjust(rotation=45)

    await rules.show_art(ctx, {"name": "rainbow"})

    assert ctx.device._redraw is None


@pytest.mark.asyncio
async def test_a_rotation_of_zero_keeps_the_random_piece(ctx):
    await ctx.device.adjust(rotation=0)

    await rules.show_art(ctx, {})

    assert ctx.device._redraw is None


@pytest.mark.asyncio
async def test_a_piece_deleted_since_it_was_picked_falls_back_to_random(
    tmp_path, ctx, caplog
):
    (tmp_path / "gone.txt").write_text(art.ARTWORKS["rainbow"].strip("\n") + "\n")
    await rules.show_art(ctx, {"name": "gone"})
    (tmp_path / "gone.txt").unlink()

    await rules.art_channel(ctx)

    assert len(ctx.board.grids) == 2
    assert "no piece named 'gone' any more" in caplog.text


# -- the message --------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_text_goes_to_the_board_as_sent(ctx):
    await rules.text(ctx, {"text": "BACK IN AN HOUR"})

    assert ctx.board.sent == ["BACK IN AN HOUR"]
    assert ctx.device.channel == "message"
    assert ctx.device.message == "BACK IN AN HOUR"
    assert ctx.device.showing == "Message: BACK IN AN HOUR"


@pytest.mark.asyncio
async def test_text_from_a_template_still_goes_up(ctx):
    # A template renders with whatever whitespace the YAML block left it, and
    # one that counts something renders to a number rather than a string.
    await rules.text(ctx, {"text": "  71 DEGREES\n"})
    await rules.text(ctx, {"text": 71})

    assert ctx.board.sent == ["71 DEGREES", "71"]


@pytest.mark.asyncio
async def test_nothing_to_say_leaves_the_board_alone(ctx, caplog):
    await rules.text(ctx, {"text": "DINNER"})

    # The Cloud API rejects a blank message, so none of these is worth sending.
    for data in ({}, {"text": ""}, {"text": "   "}, {"text": None}):
        await rules.text(ctx, data)

    assert ctx.board.sent == ["DINNER"]
    assert ctx.device.message == "DINNER"
    assert caplog.text.count("no text") == 4


@pytest.mark.asyncio
async def test_an_empty_message_from_the_device_clears_the_board(ctx):
    await rules.text(ctx, {"text": "DINNER"})

    # The text entity set to nothing: the board goes blank, which the Cloud
    # API only does for a grid of blank chips.
    await ctx.device.adjust(message="")

    assert ctx.board.grids == [charcodes.blank_grid()]
    assert ctx.device.showing == "Message"


# -- the eggs -----------------------------------------------------------------


def right_of_the_hen(grid):
    """Each row's label and count, as the text the board will show."""
    return [
        "".join(charcodes.CODE_TO_CHAR[code] for code in row[rules.LABEL_COL :])
        for row in grid
    ]


@pytest.mark.asyncio
async def test_today_is_a_count_and_the_averages_keep_their_decimals(ctx):
    await rules.eggs(ctx, {"today": 3, "mtd": 2.75, "ytd": 2.413})

    [grid] = ctx.board.grids
    assert right_of_the_hen(grid) == [
        "TODAY  3",
        "MTD 2.75",
        "YTD 2.41",
    ]
    assert ctx.device.channel == "eggs"


@pytest.mark.asyncio
async def test_the_numbers_are_kept_for_tuning_back_to_eggs(ctx):
    await rules.eggs(ctx, {"today": 3, "mtd": 2.75, "ytd": 2.41})
    await rules.text(ctx, {"text": "DINNER"})

    await ctx.device.tune("eggs")

    assert right_of_the_hen(ctx.board.grids[-1]) == [
        "TODAY  3",
        "MTD 2.75",
        "YTD 2.41",
    ]


@pytest.mark.asyncio
async def test_eggs_never_sent_are_question_marks(ctx):
    await ctx.device.tune("eggs")

    [grid] = ctx.board.grids
    assert right_of_the_hen(grid) == [
        "TODAY  ?",
        "MTD    ?",
        "YTD    ?",
    ]


@pytest.mark.asyncio
async def test_an_average_gives_up_a_decimal_to_fit(ctx):
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
async def test_the_hen_is_not_always_the_same_one(ctx):
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
async def test_a_missing_count_is_a_question_mark(ctx):
    await rules.eggs(ctx, {"today": 3})

    [grid] = ctx.board.grids
    assert right_of_the_hen(grid) == [
        "TODAY  3",
        "MTD    ?",
        "YTD    ?",
    ]


@pytest.mark.asyncio
async def test_an_average_of_a_hundred_or_more_drops_its_decimals(ctx):
    await rules.eggs(ctx, {"today": 1, "mtd": 123.4, "ytd": 1207})

    assert right_of_the_hen(ctx.board.grids[0])[1:] == ["MTD  123", "YTD 1207"]


@pytest.mark.asyncio
async def test_counts_arriving_as_text_still_count(ctx):
    # A Home Assistant template renders to a string, not a number.
    await rules.eggs(ctx, {"today": "3", "mtd": "2.75", "ytd": "2.41"})

    [grid] = ctx.board.grids
    assert right_of_the_hen(grid) == [
        "TODAY  3",
        "MTD 2.75",
        "YTD 2.41",
    ]


@pytest.mark.asyncio
async def test_the_values_line_up_against_the_right_edge(ctx):
    # TODAY is two chips longer than the other labels, so its value starts
    # further right -- but all three still end on the board's last chip.
    await rules.eggs(ctx, {"today": 7, "mtd": 2.75, "ytd": 12.3})

    [grid] = ctx.board.grids
    assert [row[-1] for row in grid] == [charcodes.encode_char(c) for c in "753"]


@pytest.mark.asyncio
async def test_todays_shorter_field_says_when_it_runs_out(ctx):
    # Three chips, TODAY having taken the other two, so four digits do not go.
    await rules.eggs(ctx, {"today": 1000, "mtd": 1.2, "ytd": 1.2})

    assert right_of_the_hen(ctx.board.grids[0])[0] == "TODAY99+"


def test_a_label_leaving_no_room_for_its_value_is_an_error(monkeypatch):
    monkeypatch.setattr(rules, "EGG_ROWS", (("YESTERDAY", "today", 0),))

    with pytest.raises(ValueError, match="too few"):
        rules.eggs_grid({"today": 1})


@pytest.mark.asyncio
async def test_a_count_too_big_for_four_chips_says_so(ctx):
    await rules.eggs(ctx, {"today": 1, "mtd": 1.2, "ytd": 10000})

    assert right_of_the_hen(ctx.board.grids[0])[2] == "YTD 999+"


# -- the channels, as a device sees them ----------------------------------------


@pytest.mark.asyncio
async def test_hold_draws_nothing(ctx):
    await rules.text(ctx, {"text": "DINNER"})

    await ctx.device.tune("hold")

    assert ctx.board.sent == ["DINNER"]
    assert ctx.board.grids == []
    assert ctx.device.showing == "Hold"


@pytest.mark.asyncio
async def test_the_channel_survives_a_restart(tmp_path, ctx):
    await rules.text(ctx, {"text": "DINNER"})

    again = FakeContext(tmp_path)
    await again.device.start(again)

    # Back on Message, saying the same thing, without being asked again.
    assert again.device.channel == "message"
    assert again.board.sent == ["DINNER"]
    await asyncio.sleep(0)
    again.device.stop()
