import pytest

from vestaboard_ha import art, charcodes


def test_every_artwork_is_the_right_shape_and_encodes():
    for name, piece in art.ARTWORKS.items():
        lines = art.rows(piece)
        assert len(lines) == art.HEIGHT, name
        assert all(len(line) == art.WIDTH for line in lines), name

        grid = art.to_grid(piece)
        assert len(grid) == charcodes.ROWS, name
        assert all(len(row) == charcodes.COLS for row in grid), name


def test_short_and_blank_lines_are_padded_out():
    assert art.rows("\nRGB\n\n\n") == ["RGB".ljust(15), " " * 15, " " * 15]


def test_wrong_shape_is_rejected():
    with pytest.raises(ValueError):
        art.rows("\nR\nG\n")  # two rows
    with pytest.raises(ValueError):
        art.rows("\n" + "R" * 16 + "\nG\nB\n")


def test_the_block_is_centered_on_the_board():
    grid = art.to_grid("\n" + "R" * 15 + "\n\n\n")  # one row of red, two blank

    # 3 rows of 15 on a 6x22 board: one blank row above, three blank columns
    # to the left.
    assert grid[0] == [charcodes.BLANK] * charcodes.COLS
    assert grid[1][2] == charcodes.BLANK
    assert grid[1][3] == charcodes.RED
    assert grid[1][17] == charcodes.RED
    assert grid[1][18] == charcodes.BLANK


def test_colors_and_letters_both_work():
    assert art.encode_chip("R") == charcodes.RED
    assert art.encode_chip(" ") == charcodes.BLANK
    assert art.encode_chip("#") == charcodes.FILLED
    assert art.encode_chip("!") == charcodes.encode_char("!")
    with pytest.raises(charcodes.UnsupportedCharacter):
        art.encode_chip("☃")


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
