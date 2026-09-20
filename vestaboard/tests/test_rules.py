from datetime import date

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

    assert ctx.board.grids == [art.to_grid(art.ARTWORKS["rainbow"].art)]


@pytest.mark.asyncio
async def test_a_saved_piece_goes_to_the_board_too(tmp_path):
    ctx = FakeContext(tmp_path)
    (tmp_path / "captured.txt").write_text(
        art.ARTWORKS["rainbow"].art.strip("\n") + "\n"
    )

    await rules.show_art(ctx, {"name": "captured"})

    assert ctx.board.grids == [art.to_grid(art.ARTWORKS["rainbow"].art)]


@pytest.mark.asyncio
async def test_no_name_means_any_artwork_in_the_art_category(tmp_path):
    ctx = FakeContext(tmp_path)

    await rules.show_art(ctx, {})

    [grid] = ctx.board.grids
    assert grid in [
        art.to_grid(piece.art)
        for piece in art.ARTWORKS.values()
        if piece.category == art.DEFAULT_CATEGORY
    ]
    assert len(grid) == charcodes.ROWS


@pytest.mark.asyncio
async def test_a_category_picks_within_it(tmp_path):
    ctx = FakeContext(tmp_path)

    await rules.show_art(ctx, {"category": "bedtime"})

    # The bedtime pieces and nothing else, so the daytime art stays out of it.
    [grid] = ctx.board.grids
    assert grid in [
        art.to_grid(piece.art)
        for piece in art.ARTWORKS.values()
        if piece.category == "bedtime"
    ]


@pytest.mark.asyncio
async def test_a_named_piece_comes_up_whatever_the_category_says(tmp_path):
    ctx = FakeContext(tmp_path)

    await rules.show_art(ctx, {"name": "rainbow", "category": "bedtime"})

    assert ctx.board.grids == [art.to_grid(art.ARTWORKS["rainbow"].art)]


@pytest.mark.asyncio
async def test_the_text_goes_to_the_board_as_sent(tmp_path):
    ctx = FakeContext(tmp_path)

    await rules.text(ctx, {"text": "BACK IN AN HOUR"})

    assert ctx.board.sent == ["BACK IN AN HOUR"]


@pytest.mark.asyncio
async def test_text_from_a_template_still_goes_up(tmp_path):
    ctx = FakeContext(tmp_path)

    # A template renders with whatever whitespace the YAML block left it, and
    # one that counts something renders to a number rather than a string.
    await rules.text(ctx, {"text": "  71 DEGREES\n"})
    await rules.text(ctx, {"text": 71})

    assert ctx.board.sent == ["71 DEGREES", "71"]


@pytest.mark.asyncio
async def test_nothing_to_say_leaves_the_board_alone(tmp_path, caplog):
    ctx = FakeContext(tmp_path)

    # The Cloud API rejects a blank message, so none of these is worth sending.
    for data in ({}, {"text": ""}, {"text": "   "}, {"text": None}):
        await rules.text(ctx, data)

    assert ctx.board.sent == []
    assert caplog.text.count("no text") == 4


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


def right_of_the_smoke(grid):
    """Each row's label and reading, as the text the board will show."""
    return [
        "".join(charcodes.CODE_TO_CHAR[code] for code in row[rules.SMOKE_COLS :])
        for row in grid
    ]


@pytest.mark.asyncio
async def test_the_smoker_board_is_two_temperatures_and_a_timer(tmp_path):
    ctx = FakeContext(tmp_path)

    await rules.smoker(ctx, {"food": 135, "air": 227, "duration": "2:06:33"})

    [grid] = ctx.board.grids
    assert right_of_the_smoke(grid) == [
        "   FOOD 135F",
        "    AIR 227F",
        "  TIMER 2:06",
    ]


@pytest.mark.asyncio
async def test_no_duration_means_no_timer_row(tmp_path):
    ctx = FakeContext(tmp_path)

    await rules.smoker(ctx, {"food": 135, "air": 227})

    [grid] = ctx.board.grids
    assert right_of_the_smoke(grid) == [
        "   FOOD 135F",
        "    AIR 227F",
        "            ",
    ]


@pytest.mark.asyncio
async def test_a_duration_that_renders_to_nothing_is_no_duration(tmp_path):
    ctx = FakeContext(tmp_path)

    # What a template comes out as while the smoker is off.
    for duration in (None, "", "   "):
        await rules.smoker(ctx, {"food": 135, "air": 227, "duration": duration})

    assert all(
        right_of_the_smoke(grid)[2].strip() == "" for grid in ctx.board.grids
    )


def test_the_smoke_is_written_out_to_the_chips_it_fills():
    chips = art.rows(rules.SMOKE)  # raises if the smoke does not parse

    assert len(chips) == charcodes.ROWS
    assert [len(row) for row in chips] == [rules.SMOKE_COLS] * charcodes.ROWS


def test_the_smoke_fills_the_chips_left_of_the_readings():
    grid = rules.smoker_grid({"food": 135, "air": 227, "duration": 60})

    assert len(grid) == charcodes.ROWS
    assert all(len(row) == charcodes.COLS for row in grid)
    assert [row[: rules.SMOKE_COLS] for row in grid] == chips_of(rules.SMOKE)


def test_the_ember_stays_lit_with_nothing_to_count():
    # The timer's row is the one the smoke's last chip is in, so leaving the
    # row off must not take the ember with it.
    grid = rules.smoker_grid({"food": 135, "air": 227})

    assert grid[2][: rules.SMOKE_COLS] == chips_of(rules.SMOKE)[2]


@pytest.mark.asyncio
async def test_a_duration_can_arrive_however_the_automation_has_it(tmp_path):
    ctx = FakeContext(tmp_path)

    # Seconds, which is what Home Assistant's own durations are; a timer
    # entity's remaining; the same thing written without its seconds; and a
    # template, which renders to a string.
    for duration in (7593, "2:06:33", "2:06", "7593"):
        await rules.smoker(ctx, {"food": 135, "air": 227, "duration": duration})

    assert [right_of_the_smoke(grid)[2] for grid in ctx.board.grids] == [
        "  TIMER 2:06"
    ] * 4


@pytest.mark.asyncio
async def test_a_countdown_keeps_the_minutes_it_has_not_finished(tmp_path):
    ctx = FakeContext(tmp_path)

    # Seconds are dropped rather than rounded: 6:59 to go is still six minutes.
    await rules.smoker(ctx, {"food": 135, "air": 227, "duration": "0:06:59"})

    assert right_of_the_smoke(ctx.board.grids[0])[2] == "  TIMER 0:06"


@pytest.mark.asyncio
async def test_a_cook_that_has_run_over_sits_at_zero(tmp_path):
    ctx = FakeContext(tmp_path)

    await rules.smoker(ctx, {"food": 135, "air": 227, "duration": -30})

    assert right_of_the_smoke(ctx.board.grids[0])[2] == "  TIMER 0:00"


@pytest.mark.asyncio
async def test_a_long_cook_takes_the_chip_it_needs_from_every_row(tmp_path):
    ctx = FakeContext(tmp_path)

    await rules.smoker(ctx, {"food": 135, "air": 227, "duration": "12:06:00"})

    # The whole board steps left together, so the readings stay in a column.
    assert right_of_the_smoke(ctx.board.grids[0]) == [
        "  FOOD  135F",
        "   AIR  227F",
        " TIMER 12:06",
    ]


@pytest.mark.asyncio
async def test_temperatures_are_whole_degrees_however_they_arrive(tmp_path):
    ctx = FakeContext(tmp_path)

    # A Home Assistant template renders to a string, and a probe reads in
    # tenths; neither is worth a chip on a board this size.
    await rules.smoker(ctx, {"food": "135.4", "air": 226.6})

    assert right_of_the_smoke(ctx.board.grids[0])[:2] == [
        "   FOOD 135F",
        "    AIR 227F",
    ]


@pytest.mark.asyncio
async def test_a_reading_that_is_not_a_number_is_a_question_mark(tmp_path):
    ctx = FakeContext(tmp_path)

    # An unplugged probe, and a duration that is not a length of time.
    await rules.smoker(ctx, {"food": 135, "air": "unavailable", "duration": "soon"})

    assert right_of_the_smoke(ctx.board.grids[0]) == [
        "   FOOD 135F",
        "    AIR    ?",
        "  TIMER    ?",
    ]


@pytest.mark.asyncio
async def test_a_reading_too_wide_for_its_chips_is_a_question_mark(tmp_path):
    ctx = FakeContext(tmp_path)

    # Nothing about a cook is that hot or that long; the sensor is broken.
    await rules.smoker(ctx, {"food": 1e9, "air": 227, "duration": "10000:00"})

    assert right_of_the_smoke(ctx.board.grids[0]) == [
        "   FOOD    ?",
        "    AIR 227F",
        "  TIMER    ?",
    ]


@pytest.mark.asyncio
async def test_the_readings_line_up_against_the_right_edge(tmp_path):
    ctx = FakeContext(tmp_path)

    # Three labels of three different lengths, and the readings still end on
    # the board's last chip.
    await rules.smoker(ctx, {"food": 95, "air": 227, "duration": "1:30:00"})

    [grid] = ctx.board.grids
    assert [row[-1] for row in grid] == [charcodes.encode_char(c) for c in "FF0"]


def test_a_smoke_that_is_not_the_size_of_its_chips_is_an_error(monkeypatch):
    monkeypatch.setattr(rules, "SMOKE", "⬜⬜⬜⬜\n⬜⬜⬜⬜\n⬜⬜⬜⬜")

    with pytest.raises(ValueError, match="the smoke is 3 rows of 3 chips"):
        rules.smoker_grid({"food": 135, "air": 227})


def test_a_label_leaving_no_room_for_the_smoke_is_an_error(monkeypatch):
    monkeypatch.setattr(rules, "SMOKER_ROWS", (("TEMPERATURE", "food"),))

    with pytest.raises(ValueError, match="no room for the smoke"):
        rules.smoker_grid({"food": 135})


def date_column(grid):
    """The date down the left, as the text the board will show."""
    return [
        "".join(charcodes.CODE_TO_CHAR[code] for code in row[: rules.DATE_COLS]).strip()
        for row in grid
    ]


def board_text(grid):
    """The whole board as text, with a # for each colored chip."""
    return [
        "".join(charcodes.CODE_TO_CHAR.get(code, "#") for code in row) for row in grid
    ]


def condition_chips(grid, data):
    """The middle of the board: the chips the condition was drawn as."""
    col = rules.condition_col(len(rules.temperatures(data)[0]))
    return [row[col : col + rules.ICON_COLS] for row in grid]


A_FORECAST = {"condition": "rainy", "high": 21, "low": 9}
LEAP_DAY = date(2024, 2, 29)

#: What weather.get_forecasts gives for a day, whose three fields an automation
#: copies into the event under the names they already have.
AN_ENTRY = {
    "datetime": "2024-02-29T00:00:00-08:00",
    "condition": "rainy",
    "temperature": 21,
    "templow": 9,
    "precipitation_probability": 80,
    "wind_speed": 11.2,
}


def test_every_condition_is_written_out_to_the_chips_it_fills():
    for condition, icon in (
        *rules.CONDITIONS.items(),
        ("?", rules.UNKNOWN_CONDITION),
    ):
        chips = art.rows(icon)  # raises if the condition does not parse

        assert len(chips) == charcodes.ROWS, condition
        # Every row to the last chip, so none leans on being padded out.
        assert [len(row) for row in chips] == [rules.ICON_COLS] * charcodes.ROWS, (
            condition
        )


def test_every_home_assistant_condition_can_be_drawn():
    # The fifteen a weather entity can report; anything else is not a condition
    # Home Assistant has, whichever integration the forecast came from.
    assert set(rules.CONDITIONS) == {
        "clear-night",
        "cloudy",
        "exceptional",
        "fog",
        "hail",
        "lightning",
        "lightning-rainy",
        "partlycloudy",
        "pouring",
        "rainy",
        "snowy",
        "snowy-rainy",
        "sunny",
        "windy",
        "windy-variant",
    }


def test_the_board_is_the_date_the_condition_and_the_temperatures():
    grid = rules.forecast_grid(A_FORECAST, today=LEAP_DAY)

    # The date left, the cloud in the middle, the readings on the last chip.
    assert board_text(grid) == [
        "THU  ##   70 21",
        "FEB ####  48  9",
        "29  : :    F  C",
    ]


def test_the_readings_take_what_they_need_and_the_middle_gets_the_rest():
    # A Celsius that wants three chips takes the one the two-chip board left
    # in the middle; either way the readings end on the board's last chip.
    freezing = board_text(
        rules.forecast_grid({**A_FORECAST, "high": -2, "low": -11}, today=LEAP_DAY)
    )

    assert freezing == [
        "THU  ##  28  -2",
        "FEB #### 12 -11",
        "29  : :   F   C",
    ]

    # Three chips in both columns is as wide as readings get -- a 100F day
    # whose night is -20F, which is no weather at all -- and there the
    # condition gives up its own room rather than the readings shrinking.
    widest = board_text(
        rules.forecast_grid({**A_FORECAST, "high": 38, "low": -29}, today=LEAP_DAY)
    )

    assert widest == [
        "THU ##  100  38",
        "FEB#### -20 -29",
        "29 : :    F   C",
    ]


def test_a_column_is_as_wide_as_the_widest_reading_in_it():
    assert rules.temperatures({"high": 21, "low": 9}) == ("70 21", "48  9", " F  C")
    assert rules.temperatures({"high": 38, "low": 24}) == ("100 38", " 75 24", "  F  C")
    assert rules.temperatures({"high": -2, "low": -11}) == ("28  -2", "12 -11", " F   C")
    # Never narrower than two, so a 9C morning and a 10C one look the same.
    assert rules.temperatures({"high": 9, "low": 3}) == ("48  9", "37  3", " F  C")


def test_the_automation_sends_celsius_and_fahrenheit_is_ours_to_work_out():
    # Rounded, not truncated: 37.6C is 99.7F, which is a 100F day, and the
    # -12.4C morning is 9.7F rather than the 9F that dropping the decimal gives.
    assert rules.temperatures({"high": 37.6, "low": -12.4})[:2] == ("100  38", " 10 -12")


def test_a_board_whose_home_assistant_is_fahrenheit_says_so():
    said = rules.temperatures({"high": 70, "low": 48, "unit": "F"})

    # The same two temperatures as the Celsius board, sent the other way round.
    assert said == ("70 21", "48  9", " F  C")


def test_the_unit_can_be_the_weather_entity_s_own_answer():
    # What state_attr(..., 'temperature_unit') renders to, degree sign and all.
    for fahrenheit in ("°F", "f", " Fahrenheit "):
        assert rules.temperatures({"high": 70, "unit": fahrenheit})[0] == "70 21", (
            fahrenheit
        )

    for celsius in ("°C", "c", "CELSIUS", "", None):
        assert rules.temperatures({"high": 21, "unit": celsius})[0] == "70 21", celsius


def test_the_unit_answers_to_the_name_the_entity_gives_it():
    assert rules.temperatures({"high": 70, "temperature_unit": "°F"})[0] == "70 21"


def test_something_that_is_not_a_unit_is_read_as_celsius_and_logged(caplog):
    assert rules.temperatures({"high": 21, "unit": "kelvin"})[0] == "70 21"
    assert "not a unit" in caplog.text


def test_a_fahrenheit_board_still_reads_a_freezing_morning():
    said = rules.temperatures({"high": 10, "low": -20, "unit": "F"})

    assert said[:2] == (" 10 -12", "-20 -29")


def test_a_temperature_that_is_missing_or_is_not_one_is_a_question_mark(caplog):
    assert rules.temperatures({"low": "unavailable"})[:2] == (" ?  ?", " ?  ?")
    assert "forecast" in caplog.text


def test_a_forecast_entry_s_own_names_are_taken_too():
    assert rules.forecast_grid(AN_ENTRY) == rules.forecast_grid(
        A_FORECAST, today=LEAP_DAY
    )


def test_our_own_names_win_over_the_forecast_s():
    said = rules.temperatures({"high": 30, "temperature": 21, "low": 20, "templow": 9})

    assert said[:2] == ("86 30", "68 20")


def test_a_condition_we_cannot_draw_says_so_rather_than_guessing(caplog):
    data = {**A_FORECAST, "condition": "meteor-shower"}

    grid = rules.forecast_grid(data, today=LEAP_DAY)

    assert condition_chips(grid, data) == chips_of(rules.UNKNOWN_CONDITION)
    assert "meteor-shower" in caplog.text
    # The rest of the board is still the board.
    assert date_column(grid) == ["THU", "FEB", "29"]


def test_a_condition_is_taken_however_the_automation_spelled_it():
    data = {**A_FORECAST, "condition": " Partlycloudy\n"}

    grid = rules.forecast_grid(data, today=LEAP_DAY)

    assert condition_chips(grid, data) == chips_of(rules.CONDITIONS["partlycloudy"])


def test_the_automation_can_say_which_day_it_is():
    # What a template or a forecast's own datetime renders to, both of which an
    # automation knows the timezone of better than we do.
    for sent in ("2024-02-29", "2024-02-29T07:00:00-08:00"):
        assert date_column(rules.forecast_grid({"date": sent})) == ["THU", "FEB", "29"]


def test_a_date_that_is_not_one_falls_back_to_today(caplog):
    grid = rules.forecast_grid({"date": "tomorrow"}, today=LEAP_DAY)

    assert date_column(grid) == ["THU", "FEB", "29"]
    assert "not a date" in caplog.text


def test_no_date_at_all_is_the_day_the_board_went_up():
    grid = rules.forecast_grid({"condition": "sunny"})

    assert date_column(grid) == [
        date.today().strftime("%a").upper(),
        date.today().strftime("%b").upper(),
        str(date.today().day),
    ]


def test_a_condition_that_is_not_the_size_of_its_chips_is_an_error(monkeypatch):
    monkeypatch.setitem(rules.CONDITIONS, "sunny", "⬜⬜⬜⬜⬜\n⬜⬜⬜⬜⬜\n⬜⬜⬜⬜⬜")

    with pytest.raises(ValueError, match="a condition is 3 rows of 4 chips"):
        rules.forecast_grid({"condition": "sunny"})


def test_readings_that_would_crowd_out_the_condition_are_an_error(monkeypatch):
    # Not something a temperature can do; something a change to these could.
    monkeypatch.setattr(rules, "MIN_TEMP_WIDTH", 5)

    with pytest.raises(ValueError, match="too few"):
        rules.forecast_grid(A_FORECAST)


@pytest.mark.asyncio
async def test_the_forecast_board_goes_to_the_board(tmp_path):
    ctx = FakeContext(tmp_path)

    await rules.forecast(ctx, A_FORECAST)

    [grid] = ctx.board.grids
    assert len(grid) == charcodes.ROWS
    assert all(len(row) == charcodes.COLS for row in grid)
    assert condition_chips(grid, A_FORECAST) == chips_of(rules.CONDITIONS["rainy"])
