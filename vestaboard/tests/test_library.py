import pytest

from vestaboard_ha import art, charcodes
from vestaboard_ha.library import Library

RED_ROW = "🟥" * charcodes.COLS
A_PIECE = f"{RED_ROW}\n\n\n"
ANOTHER_PIECE = f"{'🟦' * charcodes.COLS}\n\n\n"


@pytest.fixture
def library(tmp_path):
    return Library(tmp_path / "art")


def write(library, name, text=A_PIECE, category=None):
    """Save a piece the way a hand would: a file, in a directory if it has one."""
    directory = library.directory if category is None else library.directory / category
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.txt").write_text(text, encoding="utf-8")


def test_a_directory_that_is_not_there_is_simply_no_saved_pieces(library):
    assert library.saved() == {}
    assert library.pieces() == art.ARTWORKS


def test_a_file_is_a_piece_named_after_it(library):
    write(library, "sunrise")

    assert library.saved() == {"sunrise": art.Piece(A_PIECE)}
    assert library.grid("sunrise") == art.to_grid(A_PIECE)


def test_saved_pieces_come_after_the_built_in_ones(library):
    write(library, "zebra")
    write(library, "aardvark")

    names = list(library.pieces())

    assert names[: len(art.ARTWORKS)] == list(art.ARTWORKS)
    assert names[len(art.ARTWORKS) :] == ["aardvark", "zebra"]


def test_a_file_shadows_a_built_in_piece_of_the_same_name(library):
    write(library, "rainbow")

    assert library.pieces()["rainbow"] == art.Piece(A_PIECE)
    # In the place the built-in piece had, so the gallery does not jump around.
    index = list(library.pieces()).index("rainbow")
    assert index == list(art.ARTWORKS).index("rainbow")


def test_a_file_written_on_windows_still_parses(library):
    write(library, "crlf", A_PIECE.replace("\n", "\r\n"))

    assert library.grid("crlf") == art.to_grid(A_PIECE)


def test_an_unknown_name_is_rejected(library):
    with pytest.raises(ValueError, match="no artwork named"):
        library.grid("nonesuch")


def test_a_random_piece_is_never_the_one_already_up(library, monkeypatch):
    monkeypatch.setattr(art, "ARTWORKS", {})
    write(library, "one", A_PIECE)
    write(library, "two", ANOTHER_PIECE)

    seen = [library.grid() for _ in range(10)]

    assert all(a != b for a, b in zip(seen[:-1], seen[1:], strict=True))
    assert len({tuple(map(tuple, grid)) for grid in seen}) == 2


def test_a_broken_file_is_left_out_of_the_rotation(library, monkeypatch, caplog):
    monkeypatch.setattr(art, "ARTWORKS", {"good": art.Piece(A_PIECE)})
    write(library, "broken", "🟥HI\n")

    assert all(library.grid() == art.to_grid(A_PIECE) for _ in range(5))
    assert "broken" in caplog.text
    # It is still a piece, so the gallery can show it and say what is wrong.
    assert "broken" in library.pieces()


def test_nothing_showable_is_an_error(library, monkeypatch):
    monkeypatch.setattr(art, "ARTWORKS", {})

    with pytest.raises(ValueError, match="no art"):
        library.grid()


def test_a_capture_reads_back_as_the_grid_it_came_from(library):
    grid = art.to_grid(art.ARTWORKS["rainbow"].art)

    saved = library.capture(grid)

    assert saved == ("capture-1", True)
    assert (library.directory / "capture-1.txt").exists()
    assert library.grid("capture-1") == grid


def test_a_capture_joins_the_rotation(library, monkeypatch):
    monkeypatch.setattr(art, "ARTWORKS", {})
    library.capture(art.to_grid(A_PIECE))

    assert library.grid() == library.grid("capture-1")


def test_captures_are_numbered_past_the_highest_there_has_been(library):
    write(library, "capture-1")
    write(library, "capture-7")
    write(library, "capture-nope")

    assert library.capture(art.to_grid(art.ARTWORKS["rainbow"].art)).name == "capture-8"


def test_capturing_the_same_board_twice_keeps_the_one_file(library):
    grid = art.to_grid(art.ARTWORKS["rainbow"].art)

    first = library.capture(grid)
    second = library.capture(grid)

    assert first == ("capture-1", True)
    assert second == ("capture-1", False)
    assert len(list(library.directory.glob("*.txt"))) == 1


def test_a_blank_board_is_not_worth_capturing(library):
    with pytest.raises(ValueError, match="blank"):
        library.capture(charcodes.blank_grid())

    assert not library.directory.exists()


def test_deleting_a_saved_piece_takes_the_file_with_it(library):
    write(library, "sunrise")

    library.delete("sunrise")

    assert library.saved() == {}
    assert not (library.directory / "sunrise.txt").exists()


def test_a_built_in_piece_has_no_file_to_delete(library):
    with pytest.raises(ValueError, match="art.py"):
        library.delete("rainbow")

    assert "rainbow" in library.pieces()


def test_deleting_what_is_not_there_says_so(library):
    write(library, "sunrise")
    library.delete("sunrise")

    with pytest.raises(ValueError, match="no saved piece"):
        library.delete("sunrise")
    with pytest.raises(ValueError, match="no saved piece"):
        library.delete("../escape")


def test_a_deleted_piece_leaves_the_rotation(library, monkeypatch):
    monkeypatch.setattr(art, "ARTWORKS", {})
    write(library, "one", A_PIECE)
    write(library, "two", ANOTHER_PIECE)

    library.delete("two")

    assert all(library.grid() == art.to_grid(A_PIECE) for _ in range(5))


def test_a_file_in_a_directory_is_a_piece_in_that_category(library):
    write(library, "sunrise")
    write(library, "moonrise", ANOTHER_PIECE, category="bedtime")

    assert library.saved() == {
        "sunrise": art.Piece(A_PIECE),
        "moonrise": art.Piece(ANOTHER_PIECE, category="bedtime"),
    }


def test_a_random_piece_comes_from_the_category_asked_for(library, monkeypatch):
    monkeypatch.setattr(art, "ARTWORKS", {})
    write(library, "day", A_PIECE)
    write(library, "night", ANOTHER_PIECE, category="bedtime")

    assert all(library.grid() == art.to_grid(A_PIECE) for _ in range(5))
    assert all(
        library.grid(category="bedtime") == art.to_grid(ANOTHER_PIECE)
        for _ in range(5)
    )


def test_a_blank_category_is_no_category_at_all(library, monkeypatch):
    monkeypatch.setattr(art, "ARTWORKS", {})
    write(library, "day", A_PIECE)
    write(library, "night", ANOTHER_PIECE, category="bedtime")

    # What a template that has nothing to say renders to.
    assert library.grid(category="") == art.to_grid(A_PIECE)
    assert library.grid(category="  ") == art.to_grid(A_PIECE)


def test_a_name_is_a_name_whatever_category_it_is_in(library):
    write(library, "moonrise", ANOTHER_PIECE, category="bedtime")

    assert library.grid("moonrise") == art.to_grid(ANOTHER_PIECE)
    # The category is only there to pick within, so a name overrides it.
    assert library.grid("moonrise", "art") == art.to_grid(ANOTHER_PIECE)


def test_a_category_with_nothing_in_it_says_which_have_something(library, monkeypatch):
    monkeypatch.setattr(art, "ARTWORKS", {})
    write(library, "night", ANOTHER_PIECE, category="bedtime")

    with pytest.raises(ValueError, match="no art to show in the 'art' category"):
        library.grid()
    with pytest.raises(ValueError, match="there is bedtime"):
        library.grid(category="daytime")


def test_a_capture_lands_in_the_category_it_was_asked_for(library):
    grid = art.to_grid(A_PIECE)

    saved = library.capture(grid, "bedtime")

    assert saved == ("capture-1", True)
    assert (library.directory / "bedtime" / "capture-1.txt").exists()
    assert library.saved()["capture-1"].category == "bedtime"
    assert library.grid("capture-1") == grid


def test_the_same_board_in_another_category_is_another_piece(library):
    grid = art.to_grid(A_PIECE)

    first = library.capture(grid)
    second = library.capture(grid, "bedtime")
    again = library.capture(grid, "bedtime")

    assert first == ("capture-1", True)
    assert second == ("capture-2", True)
    # Two pieces, shown at different times of day -- but still only the two.
    assert again == ("capture-2", False)


def test_captures_are_numbered_across_the_categories_together(library):
    write(library, "capture-4", category="bedtime")

    assert library.capture(art.to_grid(ANOTHER_PIECE)).name == "capture-5"


def test_a_category_that_is_not_one_plain_word_is_refused(library):
    with pytest.raises(ValueError, match="cannot be a category"):
        library.capture(art.to_grid(A_PIECE), "../escape")

    assert library.saved() == {}


def test_a_piece_in_a_category_is_deleted_like_any_other(library):
    write(library, "moonrise", category="bedtime")

    library.delete("moonrise")

    assert library.saved() == {}
    assert not (library.directory / "bedtime" / "moonrise.txt").exists()
    # The category is a directory of ours, so it stays for the next capture.
    assert (library.directory / "bedtime").exists()


def test_two_files_of_one_name_leave_the_top_level_one_the_piece(library, caplog):
    write(library, "moon", A_PIECE)
    write(library, "moon", ANOTHER_PIECE, category="bedtime")

    assert library.saved() == {"moon": art.Piece(A_PIECE)}
    assert "already the piece moon" in caplog.text
