import pytest

from vestaboard_ha import art, charcodes


def test_every_artwork_is_the_right_shape_and_encodes():
    for name, piece in art.ARTWORKS.items():
        chips = art.rows(piece)
        assert len(chips) == art.HEIGHT, name
        assert all(len(row) == art.WIDTH for row in chips), name

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


def test_wrong_shape_is_rejected():
    with pytest.raises(ValueError, match="rows"):
        art.rows("\n🟥\n🟩\n")
    with pytest.raises(ValueError, match="wider"):
        art.rows("\n" + "🟥" * 16 + "\n🟩\n🟦\n")


def test_short_and_blank_rows_are_padded_out():
    assert art.rows("\n🟥\n\n\n") == [
        ["🟥"] + [" "] * 14,
        [" "] * 15,
        [" "] * 15,
    ]


def test_the_block_is_centered_on_the_board():
    grid = art.to_grid("\n" + "🟥" * 15 + "\n\n\n")

    # 3 rows of 15 on a 6x22 board: one blank row above, three blank columns
    # to the left.
    assert grid[0] == [charcodes.BLANK] * charcodes.COLS
    assert grid[1][2] == charcodes.BLANK
    assert grid[1][3] == charcodes.RED
    assert grid[1][17] == charcodes.RED
    assert grid[1][18] == charcodes.BLANK


def test_squares_and_characters_both_encode():
    assert art.encode_chip("🟥") == charcodes.RED
    assert art.encode_chip("⬛") == charcodes.BLANK
    assert art.encode_chip(" ") == charcodes.BLANK
    assert art.encode_chip("P") == charcodes.encode_char("P")
    with pytest.raises(charcodes.UnsupportedCharacter):
        art.encode_chip("☃")


def test_text_and_art_share_a_piece():
    middle = art.to_grid(art.ARTWORKS["party"])[2]
    word = [charcodes.encode_char(c) for c in "PARTY!"]

    assert charcodes.RED in art.to_grid(art.ARTWORKS["party"])[1]
    assert word == [code for code in middle if code != charcodes.BLANK]


def test_a_named_artwork_comes_back(monkeypatch):
    monkeypatch.setattr(art, "_last_shown", None)
    assert art.grid("heart") == art.to_grid(art.ARTWORKS["heart"])


def test_an_unknown_name_is_rejected():
    with pytest.raises(ValueError):
        art.grid("nonesuch")


def test_random_art_never_repeats_itself(monkeypatch):
    monkeypatch.setattr(art, "_last_shown", None)

    seen = [art.grid() for _ in range(20)]

    assert all(a != b for a, b in zip(seen[:-1], seen[1:], strict=True))
    assert len({tuple(map(tuple, g)) for g in seen}) > 1
