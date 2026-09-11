import pytest

from vestaboard_ha import charcodes


def test_letters_and_digits_round_trip():
    assert charcodes.encode_char("a") == 1
    assert charcodes.encode_char("Z") == 26
    assert charcodes.encode_char("1") == 27
    assert charcodes.encode_char("0") == 36


def test_every_character_decodes_back():
    for char, code in charcodes.CHAR_TO_CODE.items():
        assert charcodes.CODE_TO_CHAR[code] == char

    assert charcodes.CODE_TO_CHAR[charcodes.BLANK] == " "
    # The colored chips are not characters and have no entry.
    assert charcodes.RED not in charcodes.CODE_TO_CHAR


def test_unsupported_character_is_rejected():
    with pytest.raises(charcodes.UnsupportedCharacter):
        charcodes.encode_char("☃")


def test_encode_lines_centers_and_pads():
    grid = charcodes.encode_lines(["HI"])

    assert len(grid) == charcodes.ROWS
    assert all(len(row) == charcodes.COLS for row in grid)
    # 22 columns, 2 characters, so 10 blanks then H I.
    assert grid[0][10] == charcodes.encode_char("H")
    assert grid[0][11] == charcodes.encode_char("I")
    assert grid[0][9] == charcodes.BLANK
    assert grid[1] == [charcodes.BLANK] * charcodes.COLS


def test_encode_lines_left_aligns_when_asked():
    grid = charcodes.encode_lines(["HI"], center=False)
    assert grid[0][0] == charcodes.encode_char("H")


def test_oversized_input_is_rejected():
    with pytest.raises(ValueError):
        charcodes.encode_lines(["X" * 23])
    with pytest.raises(ValueError):
        charcodes.encode_lines(["X"] * 7)
