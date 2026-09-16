import socket

import pytest
from aiohttp.test_utils import TestClient, TestServer

from vestaboard_ha import art, web
from vestaboard_ha.board import BoardError
from vestaboard_ha.library import Library

#: A piece is the board: 15 chips by 3.
CHIPS_PER_PIECE = 15 * 3

#: Squares and text in one piece, for the tests that want both.
A_PIECE = """
🟥🟧🟨🟩🟦🟪🟥🟧🟨🟩🟦🟪🟥🟧🟨
⬛⬛⬛⬛ P A R T Y !⬛⬛⬛⬛⬛
🟪🟦🟩🟨🟧🟥🟪🟦🟩🟨🟧🟥🟪🟦🟩
"""


class FakeBoard:
    """A board with something on it, or one that will not say what."""

    def __init__(self, grid=None, error=None):
        self.grid = grid
        self.error = error

    async def read(self):
        if self.error is not None:
            raise self.error
        return self.grid


class FakeContext:
    def __init__(self, tmp_path, board=None):
        self.art = Library(tmp_path)
        self.board = board or FakeBoard()


async def get_page(ctx, path="/"):
    """GET the gallery, following the redirect a capture answers with."""
    client = TestClient(TestServer(web.build_app(ctx)))
    await client.start_server()
    try:
        response = await client.get(path)
        return response, await response.text()
    finally:
        await client.close()


async def post_capture(ctx):
    return await post(ctx, {"capture": "board"})


async def post_delete(ctx, name):
    return await post(ctx, {"delete": name})


async def post(ctx, form):
    """Press one of the page's buttons, following the redirect it answers with."""
    client = TestClient(TestServer(web.build_app(ctx)))
    await client.start_server()
    try:
        response = await client.post("/", data=form)
        return response, await response.text()
    finally:
        await client.close()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_every_piece_gets_a_card_and_all_of_its_chips():
    html = web.page(art.ARTWORKS)

    for name in art.ARTWORKS:
        assert f">{name}</h2>" in html
    assert html.count("<article") == len(art.ARTWORKS)
    # The piece itself, 15x3, and not the blank surround the board centers it in.
    assert html.count('class="chip') == CHIPS_PER_PIECE * len(art.ARTWORKS)


def test_a_heart_is_drawn_as_one_and_not_as_a_degree_sign():
    html = web.page({"love": "\n❤️🟥❤️\n"})

    # Code 62 is the degree sign in the character table, but this board is a
    # Note, which draws it as a red heart -- so the gallery has to as well.
    assert html.count('class="chip heart"') == 2
    assert "&#10084;" in html
    assert "°" not in html


def test_a_short_line_is_padded_out_with_unlit_flaps():
    html = web.page({"corner": "\n🟥🟥🟥\n🟥\n\n"})

    # Three rows of the widest line's three chips, all but two of them unlit.
    assert html.count('class="chip') == 9
    assert html.count('<span class="chip"></span>') == 5


def test_cards_keep_the_order_art_py_has_them_in():
    html = web.page(art.ARTWORKS)
    assert sorted(art.ARTWORKS, key=html.index) == list(art.ARTWORKS)


def test_colors_and_characters_both_show_up():
    html = web.page({"party": A_PIECE})

    assert '<span class="chip red"></span>' in html
    assert '<span class="chip violet"></span>' in html
    assert '<span class="chip">P</span>' in html
    assert '<span class="chip"></span>' in html  # an unlit flap


def test_a_piece_that_no_longer_encodes_says_so():
    taller_than_the_board = "\n" + "🟥\n" * 7
    html = web.page({"good": A_PIECE, "broken": taller_than_the_board})

    assert "does not encode" in html
    assert "7 rows" in html
    # The rest of the gallery is still there.
    assert html.count('class="chip') == CHIPS_PER_PIECE


def test_names_and_characters_are_escaped():
    html = web.page({"<script>": "\n Q &\n\n\n"})

    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert '<span class="chip">&amp;</span>' in html


def test_an_empty_gallery_says_what_to_do():
    html = web.page({})

    assert "<article" not in html
    assert "art.py" in html


def test_one_piece_is_not_pluralized():
    assert "1 piece." in web.page({"rainbow": art.ARTWORKS["rainbow"]})


def test_the_page_has_no_urls_to_rewrite():
    # Ingress mounts the app under a path of its own choosing, so a relative
    # URL is the only kind that survives. Having none at all is how we are sure.
    html = web.page(art.ARTWORKS)

    assert "src=" not in html
    assert "href=" not in html


@pytest.mark.asyncio
async def test_the_gallery_is_served_as_html(tmp_path):
    response, body = await get_page(FakeContext(tmp_path))

    assert response.status == 200
    assert response.content_type == "text/html"
    assert response.headers["Cache-Control"] == "no-store"
    assert "Art gallery" in body


@pytest.mark.asyncio
async def test_the_page_follows_art_py(tmp_path, monkeypatch):
    monkeypatch.setattr(art, "ARTWORKS", {"newcomer": art.ARTWORKS["rainbow"]})

    _, body = await get_page(FakeContext(tmp_path))

    assert "newcomer" in body
    assert "rainbow" not in body


@pytest.mark.asyncio
async def test_anything_else_is_a_404(tmp_path):
    response, _ = await get_page(FakeContext(tmp_path), "/nope")

    assert response.status == 404


@pytest.mark.asyncio
async def test_serve_listens_and_stops(tmp_path):
    port = free_port()

    runner = await web.serve(FakeContext(tmp_path), port)

    assert runner is not None
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            pass
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_a_port_we_cannot_have_is_logged_not_raised(tmp_path, caplog):
    port = free_port()
    first = await web.serve(FakeContext(tmp_path), port)
    assert first is not None

    try:
        assert await web.serve(FakeContext(tmp_path), port) is None
        assert "could not listen" in caplog.text
    finally:
        await first.cleanup()


def test_the_header_offers_to_capture_the_board():
    html = web.page(art.ARTWORKS)

    assert '<form method="post">' in html
    assert "Capture the board" in html


def test_saved_pieces_are_marked_as_saved():
    html = web.page({"rainbow": art.ARTWORKS["rainbow"]}, saved={"rainbow"})

    assert '<span class="tag">saved</span>' in html
    assert web.page({"rainbow": art.ARTWORKS["rainbow"]}).count('class="tag"') == 0


def test_a_notice_is_shown_and_escaped():
    assert '<p class="notice">Captured as x.</p>' in web.page({}, notice="Captured as x.")
    assert '<p class="notice bad">' in web.page({}, notice="Nope", bad_news=True)
    assert "&lt;script&gt;" in web.page({}, notice="<script>")


@pytest.mark.asyncio
async def test_a_saved_piece_shows_up_in_the_gallery(tmp_path):
    ctx = FakeContext(tmp_path)
    ctx.art.capture(art.to_grid(art.ARTWORKS["rainbow"]))

    _, body = await get_page(ctx)

    assert ">capture-1<" in body
    assert body.count('<span class="tag">saved</span>') == 1


@pytest.mark.asyncio
async def test_capture_saves_the_board_and_says_where(tmp_path):
    grid = art.to_grid(A_PIECE)
    ctx = FakeContext(tmp_path, FakeBoard(grid))

    response, _ = await post_capture(ctx)

    assert ctx.art.saved() == {"capture-1": art.render(grid)}
    # Posting again would capture again, so the answer is a redirect.
    assert response.status == 200
    assert response.history[0].status == 303
    assert response.history[0].headers["Location"] == "/?saved=capture-1"


@pytest.mark.asyncio
async def test_the_page_after_a_capture_names_the_piece(tmp_path):
    ctx = FakeContext(tmp_path, FakeBoard(art.to_grid(A_PIECE)))
    await post_capture(ctx)

    _, body = await get_page(ctx, "/?saved=capture-1")

    assert "Captured as capture-1" in body


@pytest.mark.asyncio
async def test_capturing_the_same_board_again_says_so(tmp_path):
    ctx = FakeContext(tmp_path, FakeBoard(art.to_grid(A_PIECE)))
    await post_capture(ctx)

    response, _ = await post_capture(ctx)
    _, body = await get_page(ctx, "/?again=capture-1")

    assert response.history[0].headers["Location"] == "/?again=capture-1"
    assert "already saved as capture-1" in body


@pytest.mark.asyncio
async def test_a_name_that_is_not_ours_says_nothing(tmp_path):
    _, body = await get_page(FakeContext(tmp_path), "/?saved=%3Cscript%3E")

    assert '<p class="notice' not in body
    assert "script" not in body


@pytest.mark.asyncio
async def test_a_board_that_cannot_be_read_says_why(tmp_path):
    ctx = FakeContext(tmp_path, FakeBoard(error=BoardError("no API token configured")))

    response, body = await post_capture(ctx)

    assert response.status == 200
    assert response.history == ()
    assert "Could not capture the board: no API token configured" in body
    assert '<p class="notice bad">' in body


@pytest.mark.asyncio
async def test_a_blank_board_is_not_captured(tmp_path):
    from vestaboard_ha import charcodes

    ctx = FakeContext(tmp_path, FakeBoard(charcodes.blank_grid()))

    _, body = await post_capture(ctx)

    assert "nothing to capture" in body
    assert ctx.art.saved() == {}


def test_the_redirect_goes_back_through_ingress():
    class FakeRequest:
        def __init__(self, path):
            self.headers = {web.INGRESS_PATH_HEADER: path} if path else {}

    assert web._base_path(FakeRequest("/api/hassio_ingress/abc123/")) == (
        "/api/hassio_ingress/abc123"
    )
    assert web._base_path(FakeRequest("")) == ""
    # Nothing that would send the browser somewhere else entirely.
    assert web._base_path(FakeRequest("//elsewhere.example")) == ""
    assert web._base_path(FakeRequest("https://elsewhere.example")) == ""


def test_only_saved_pieces_can_be_deleted():
    saved = web.page({"capture-1": A_PIECE}, saved={"capture-1"})
    built_in = web.page({"rainbow": art.ARTWORKS["rainbow"]})

    assert '<button name="delete" value="capture-1"' in saved
    assert '<button name="delete"' not in built_in


def test_the_delete_button_asks_first():
    html = web.page({"capture-1": A_PIECE}, saved={"capture-1"})

    assert 'onsubmit="return confirm(&quot;Delete capture-1?&quot;)"' in html


def test_a_name_with_a_quote_in_it_does_not_break_the_asking():
    html = web.page({"it's": A_PIECE}, saved={"it's"})

    # The apostrophe reaches the confirm as text, not as the end of a string.
    assert "confirm(&quot;Delete it&#x27;s?&quot;)" in html
    assert '<button name="delete" value="it&#x27;s"' in html


@pytest.mark.asyncio
async def test_delete_removes_the_piece_and_says_so(tmp_path):
    ctx = FakeContext(tmp_path, FakeBoard(art.to_grid(A_PIECE)))
    await post_capture(ctx)

    response, _ = await post_delete(ctx, "capture-1")
    _, body = await get_page(ctx, "/?deleted=capture-1")

    assert ctx.art.saved() == {}
    assert response.history[0].status == 303
    assert response.history[0].headers["Location"] == "/?deleted=capture-1"
    assert "Deleted capture-1." in body


@pytest.mark.asyncio
async def test_deleting_what_is_not_ours_says_why(tmp_path):
    ctx = FakeContext(tmp_path)

    response, body = await post_delete(ctx, "rainbow")

    assert response.status == 200
    assert response.history == ()
    assert "Could not delete it" in body
    assert '<p class="notice bad">' in body


@pytest.mark.asyncio
async def test_a_deleted_name_that_is_not_ours_says_nothing(tmp_path):
    _, body = await get_page(FakeContext(tmp_path), "/?deleted=%3Cscript%3E")

    assert '<p class="notice' not in body


@pytest.mark.asyncio
async def test_a_piece_still_here_is_not_announced_as_deleted(tmp_path):
    ctx = FakeContext(tmp_path, FakeBoard(art.to_grid(A_PIECE)))
    await post_capture(ctx)

    _, body = await get_page(ctx, "/?deleted=capture-1")

    assert "Deleted" not in body
