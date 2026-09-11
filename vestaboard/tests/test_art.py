import pytest

from vestaboard_ha import art, charcodes


def test_every_shipped_artwork_is_15x3_and_encodes():
    for name, piece in art.ARTWORKS.items():
        chips = art.rows(piece)
        assert len(chips) == 3, name
        assert all(len(row) == 15 for row in chips), name

        grid = art.to_grid(piece)
        assert len(grid) == charcodes.ROWS, name
        assert all(len(row) == charcodes.COLS for row in grid), name


def test_a_square_is_one_chip():
    assert art.cells("🟥🟩⬛") == ["🟥", "🟩", "⬛"]


def test_a_character_is_a_space_and_the_character():
    assert art.cells(" H I") == ["H", "I"]
    assert art.cells("🟥 H🟥") == ["🟥", "H", "🟥"]


def test_two_spaces_are_a_blank_chip():
    assert art.cells("🟥    🟥") == ["🟥", " ", " ", "🟥"]


def test_an_unpaired_character_is_rejected():
    with pytest.raises(ValueError, match="unpaired"):
        art.cells("🟥HI")


def test_a_square_the_board_has_no_chip_for_is_rejected():
    with pytest.raises(ValueError, match="not a chip"):
        art.cells("🟫")


def test_a_pasted_variation_selector_is_tolerated():
    assert art.cells("⬛️⬜️") == ["⬛", "⬜"]


def test_a_piece_bigger_than_the_board_is_rejected():
    with pytest.raises(ValueError, match="rows"):
        art.rows("\n" + "🟥\n" * (charcodes.ROWS + 1))
    with pytest.raises(ValueError, match="wider"):
        art.rows("\n" + "🟥" * (charcodes.COLS + 1) + "\n🟩\n🟦\n")


def test_short_and_blank_rows_are_padded_out_to_the_widest():
    assert art.rows("\n🟥🟥🟥\n🟥\n\n") == [
        ["🟥", "🟥", "🟥"],
        ["🟥", " ", " "],
        [" ", " ", " "],
    ]


def test_a_whole_board_is_centered_on_itself():
    # What a capture is: the whole board, which centering leaves exactly alone.
    captured = charcodes.blank_grid()
    captured[0][0] = charcodes.RED
    captured[-1][-1] = charcodes.BLUE

    assert art.to_grid(art.render(captured)) == captured


def test_a_grid_renders_back_to_the_text_it_came_from():
    for piece in art.ARTWORKS.values():
        assert art.to_grid(art.render(art.to_grid(piece))) == art.to_grid(piece)

    grid = charcodes.encode_lines(["HI & 5"])
    text = art.render(grid)

    # A blank chip between characters is ⬛, the same square as anywhere else.
    assert " H I⬛ &⬛ 5" in text
    assert art.to_grid(text) == grid


def test_a_code_with_no_square_and_no_character_renders_blank(caplog):
    assert art.render_chip(charcodes.BLACK) == "⬛"
    assert art.render_chip(charcodes.FILLED) == "⬛"
    assert "no square" in caplog.text


def test_a_full_size_piece_lands_exactly_as_written():
    grid = art.to_grid("\n" + "🟥" * charcodes.COLS + "\n\n\n")

    assert grid[0] == [charcodes.RED] * charcodes.COLS
    assert grid[1] == [charcodes.BLANK] * charcodes.COLS


def test_a_smaller_piece_is_centered():
    grid = art.to_grid("\n🟥🟥🟥\n")

    # 3 chips on a 15-chip row: six blanks either side, and the single row in
    # the middle one of three.
    assert grid[0] == [charcodes.BLANK] * charcodes.COLS
    assert grid[1][5] == charcodes.BLANK
    assert grid[1][6:9] == [charcodes.RED] * 3
    assert grid[1][9] == charcodes.BLANK


def test_squares_and_characters_both_encode():
    assert art.encode_chip("🟥") == charcodes.RED
    assert art.encode_chip("⬛") == charcodes.BLANK
    assert art.encode_chip(" ") == charcodes.BLANK
    assert art.encode_chip("P") == charcodes.encode_char("P")
    with pytest.raises(charcodes.UnsupportedCharacter):
        art.encode_chip("☃")


def test_text_and_art_share_a_piece():
    grid = art.to_grid(art.ARTWORKS["party"])
    word = [charcodes.encode_char(c) for c in "PARTY!"]

    assert charcodes.RED in grid[0]
    assert word == [code for code in grid[1] if code != charcodes.BLANK]
