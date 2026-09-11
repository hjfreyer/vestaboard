import pytest

from vestaboard_ha import art, charcodes
from vestaboard_ha.library import Library

RED_ROW = "🟥" * charcodes.COLS
A_PIECE = f"{RED_ROW}\n\n\n"


@pytest.fixture
def library(tmp_path):
    return Library(tmp_path / "art")


def write(library, name, text=A_PIECE):
    library.directory.mkdir(parents=True, exist_ok=True)
    (library.directory / f"{name}.txt").write_text(text, encoding="utf-8")


def test_a_directory_that_is_not_there_is_simply_no_saved_pieces(library):
    assert library.saved() == {}
    assert library.pieces() == art.ARTWORKS


def test_a_file_is_a_piece_named_after_it(library):
    write(library, "sunrise")

    assert library.saved() == {"sunrise": A_PIECE}
    assert library.grid("sunrise") == art.to_grid(A_PIECE)


def test_saved_pieces_come_after_the_built_in_ones(library):
    write(library, "zebra")
    write(library, "aardvark")

    names = list(library.pieces())

    assert names[: len(art.ARTWORKS)] == list(art.ARTWORKS)
    assert names[len(art.ARTWORKS) :] == ["aardvark", "zebra"]


def test_a_file_shadows_a_built_in_piece_of_the_same_name(library):
    write(library, "rainbow")

    assert library.pieces()["rainbow"] == A_PIECE
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
    write(library, "two", f"{'🟦' * charcodes.COLS}\n\n\n")

    seen = [library.grid() for _ in range(10)]

    assert all(a != b for a, b in zip(seen[:-1], seen[1:], strict=True))
    assert len({tuple(map(tuple, grid)) for grid in seen}) == 2


def test_a_broken_file_is_left_out_of_the_rotation(library, monkeypatch, caplog):
    monkeypatch.setattr(art, "ARTWORKS", {"good": A_PIECE})
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
    grid = art.to_grid(art.ARTWORKS["rainbow"])

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

    assert library.capture(art.to_grid(art.ARTWORKS["rainbow"])).name == "capture-8"


def test_capturing_the_same_board_twice_keeps_the_one_file(library):
    grid = art.to_grid(art.ARTWORKS["rainbow"])

    first = library.capture(grid)
    second = library.capture(grid)

    assert first == ("capture-1", True)
    assert second == ("capture-1", False)
    assert len(list(library.directory.glob("*.txt"))) == 1


def test_a_blank_board_is_not_worth_capturing(library):
    with pytest.raises(ValueError, match="blank"):
        library.capture(charcodes.blank_grid())

    assert not library.directory.exists()
