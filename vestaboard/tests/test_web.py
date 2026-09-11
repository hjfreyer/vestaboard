import socket

import pytest
from aiohttp.test_utils import TestClient, TestServer

from vestaboard_ha import art, web

CHIPS_PER_PIECE = art.WIDTH * art.HEIGHT


async def get_page(path="/"):
    client = TestClient(TestServer(web.build_app()))
    await client.start_server()
    try:
        response = await client.get(path)
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


def test_a_short_line_is_padded_out_with_unlit_flaps():
    html = web.page({"corner": "\n🟥\n\n\n"})

    assert html.count('class="chip') == CHIPS_PER_PIECE
    assert html.count('<span class="chip"></span>') == CHIPS_PER_PIECE - 1


def test_cards_keep_the_order_art_py_has_them_in():
    html = web.page(art.ARTWORKS)
    assert sorted(art.ARTWORKS, key=html.index) == list(art.ARTWORKS)


def test_colors_and_characters_both_show_up():
    html = web.page({"party": art.ARTWORKS["party"]})

    assert '<span class="chip red"></span>' in html
    assert '<span class="chip violet"></span>' in html
    assert '<span class="chip">P</span>' in html
    assert '<span class="chip"></span>' in html  # an unlit flap


def test_a_piece_that_no_longer_encodes_says_so():
    html = web.page({"good": art.ARTWORKS["heart"], "broken": "\n🟥\n🟩\n"})

    assert "does not encode" in html
    assert "rows" in html
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
    assert "1 piece." in web.page({"heart": art.ARTWORKS["heart"]})


def test_the_page_has_no_urls_to_rewrite():
    # Ingress mounts the app under a path of its own choosing, so a relative
    # URL is the only kind that survives. Having none at all is how we are sure.
    html = web.page(art.ARTWORKS)

    assert "src=" not in html
    assert "href=" not in html


@pytest.mark.asyncio
async def test_the_gallery_is_served_as_html():
    response, body = await get_page()

    assert response.status == 200
    assert response.content_type == "text/html"
    assert response.headers["Cache-Control"] == "no-store"
    assert "Art gallery" in body


@pytest.mark.asyncio
async def test_the_page_follows_art_py(monkeypatch):
    monkeypatch.setattr(art, "ARTWORKS", {"newcomer": art.ARTWORKS["heart"]})

    _, body = await get_page()

    assert "newcomer" in body
    assert "sunset" not in body


@pytest.mark.asyncio
async def test_anything_else_is_a_404():
    response, _ = await get_page("/nope")

    assert response.status == 404


@pytest.mark.asyncio
async def test_serve_listens_and_stops():
    port = free_port()

    runner = await web.serve(port)

    assert runner is not None
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            pass
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_a_port_we_cannot_have_is_logged_not_raised(caplog):
    port = free_port()
    first = await web.serve(port)
    assert first is not None

    try:
        assert await web.serve(port) is None
        assert "could not listen" in caplog.text
    finally:
        await first.cleanup()
