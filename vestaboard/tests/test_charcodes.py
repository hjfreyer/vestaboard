import pytest

from vestaboard_ha import charcodes


def test_letters_and_digits_round_trip():
    assert charcodes.encode_char("a") == 1
    assert charcodes.encode_char("Z") == 26
    assert charcodes.encode_char("1") == 27
    assert charcodes.encode_char("0") == 36


def test_every_character_decodes_back():
    for char, code in charcodes.CHAR_TO_CODE.items():
        # Code 62 is the one flap with two spellings; see below.
        if code == charcodes.HEART:
            continue
        assert charcodes.CODE_TO_CHAR[code] == char

    assert charcodes.CODE_TO_CHAR[charcodes.BLANK] == " "
    # The colored chips are not characters and have no entry.
    assert charcodes.RED not in charcodes.CODE_TO_CHAR


def test_unsupported_character_is_rejected():
    with pytest.raises(charcodes.UnsupportedCharacter):
        charcodes.encode_char("☃")


def test_encode_lines_centers_and_pads():
    grid = charcodes.encode_lines(["HI"])
    offset = (charcodes.COLS - 2) // 2

    assert len(grid) == charcodes.ROWS
    assert all(len(row) == charcodes.COLS for row in grid)
    assert grid[0][offset] == charcodes.encode_char("H")
    assert grid[0][offset + 1] == charcodes.encode_char("I")
    assert grid[0][offset - 1] == charcodes.BLANK
    assert grid[1] == [charcodes.BLANK] * charcodes.COLS


def test_encode_lines_left_aligns_when_asked():
    grid = charcodes.encode_lines(["HI"], center=False)
    assert grid[0][0] == charcodes.encode_char("H")


def test_oversized_input_is_rejected():
    with pytest.raises(ValueError):
        charcodes.encode_lines(["X" * (charcodes.COLS + 1)])
    with pytest.raises(ValueError):
        charcodes.encode_lines(["X"] * (charcodes.ROWS + 1))


def test_the_heart_and_the_degree_sign_are_the_one_flap():
    # 62 is a degree sign on the flagship board and a red heart on a Note, so
    # both spellings encode to it. This board is a Note, so the heart is the
    # one that comes back.
    assert charcodes.encode_char("°") == charcodes.HEART
    assert charcodes.encode_char("❤") == charcodes.HEART
    assert charcodes.CODE_TO_CHAR[charcodes.HEART] == "❤"
