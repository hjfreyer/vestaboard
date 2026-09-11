"""The art gallery: every piece in ``art.py``, drawn chip for chip.

A piece is the 15x3 block, and that is what a card shows. The board centers it
on 6x22 when it is sent, but that surround is the same for every piece and
would be three quarters of every card here.

Home Assistant serves this page itself, through ingress, so the app appears in
the sidebar with an **Open Web UI** button and nothing is exposed to the network
beyond Supervisor. Ingress mounts us under a path it picks and rewrites per
session, so every URL in the page has to be relative -- easiest to guarantee by
having no URLs at all: one route, and the stylesheet inline.

Outside Home Assistant the same page is on ``ingress_port`` directly, which is
what ``docker-compose.yml`` publishes.
"""

from __future__ import annotations

import html
import logging

from aiohttp import web

from . import art, charcodes

_LOGGER = logging.getLogger(__name__)

#: Ingress reaches us inside the container, so bind everywhere.
HOST = "0.0.0.0"

#: A colored chip is a class; everything else is a character on a dark flap.
#: A black chip has no entry and so lands on that dark flap, which is what a
#: black chip looks like.
CHIP_COLORS: dict[int, str] = {
    charcodes.RED: "red",
    charcodes.ORANGE: "orange",
    charcodes.YELLOW: "yellow",
    charcodes.GREEN: "green",
    charcodes.BLUE: "blue",
    charcodes.VIOLET: "violet",
    charcodes.WHITE: "white",
}

STYLE = """
:root {
  color-scheme: light dark;
  --page: #f5f4f1;
  --ink: #1b1c20;
  --muted: #6c6e77;
  --card: #ffffff;
  --edge: #e4e2dc;
  --shadow: 0 1px 2px rgba(0, 0, 0, .07), 0 10px 24px rgba(0, 0, 0, .05);
  /* The board looks like the board whatever the page around it is doing. */
  --case: #0c0d10;
  --flap: #191a1f;
  --flap-ink: #ede8dc;
  --seam: rgba(0, 0, 0, .45);
  --red: #d63a3f;
  --orange: #e8792a;
  --yellow: #edc02f;
  --green: #33a05a;
  --blue: #2f6fd0;
  --violet: #7d4cc0;
  --white: #eae7e0;
}
@media (prefers-color-scheme: dark) {
  :root {
    --page: #121317;
    --ink: #eceae6;
    --muted: #9b9da5;
    --card: #1b1d22;
    --edge: #2c2f36;
    --shadow: none;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--page);
  color: var(--ink);
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  -webkit-text-size-adjust: 100%;
}
.top {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--page);
  border-bottom: 1px solid var(--edge);
  padding: 14px 16px;
}
.top h1 {
  margin: 0;
  font-size: 17px;
  letter-spacing: .01em;
}
.top p {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.45;
}
.inner { max-width: 720px; margin: 0 auto; }
code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: .92em;
}
.gallery {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 720px;
  margin: 0 auto;
  padding: 16px 16px 56px;
}
.piece {
  background: var(--card);
  border: 1px solid var(--edge);
  border-radius: 12px;
  box-shadow: var(--shadow);
  padding: 14px;
}
.name {
  margin: 0 0 10px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--muted);
}
.board {
  container-type: inline-size;
  display: grid;
  grid-template-columns: repeat(15, 1fr);
  gap: .5%;
  background: var(--case);
  border-radius: 8px;
  padding: 1.6%;
}
.chip {
  position: relative;
  aspect-ratio: 5 / 7;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-radius: 2px;
  background: var(--flap);
  color: var(--flap-ink);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-weight: 600;
  font-size: clamp(8px, 2.4vw, 19px);
  font-size: 4.2cqw;
  line-height: 1;
}
/* The hinge a split-flap turns on. */
.chip::after {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  top: 50%;
  border-top: 1px solid var(--seam);
}
.red { background: var(--red); }
.orange { background: var(--orange); }
.yellow { background: var(--yellow); }
.green { background: var(--green); }
.blue { background: var(--blue); }
.violet { background: var(--violet); }
.white { background: var(--white); }
.broken {
  margin: 0;
  color: var(--muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.5;
}
.empty {
  margin: 0;
  color: var(--muted);
  font-size: 14px;
}
"""


def chip(code: int) -> str:
    """One chip of the board: a color, a character, or an unlit flap."""
    color = CHIP_COLORS.get(code)
    if color is not None:
        return f'<span class="chip {color}"></span>'

    char = charcodes.CODE_TO_CHAR.get(code, " ")
    if char == " ":
        return '<span class="chip"></span>'
    return f'<span class="chip">{html.escape(char)}</span>'


def board(artwork: str, label: str) -> str:
    """An artwork's chips, encoded exactly as they are when the board gets them."""
    chips = "".join(
        chip(art.encode_chip(cell)) for row in art.rows(artwork) for cell in row
    )
    return (
        f'<div class="board" role="img" aria-label="{html.escape(label)}">'
        f"{chips}</div>"
    )


def piece(name: str, artwork: str) -> str:
    """One card. A piece that no longer encodes says so instead of vanishing."""
    try:
        body = board(artwork, f"the {name} artwork")
    except ValueError as exc:
        _LOGGER.warning("artwork %s does not encode: %s", name, exc)
        body = (
            '<p class="broken">This piece does not encode: '
            f"{html.escape(str(exc))}</p>"
        )
    return (
        '<article class="piece">'
        f'<h2 class="name">{html.escape(name)}</h2>{body}</article>'
    )


def page(artworks: dict[str, str]) -> str:
    """The whole gallery, one card per piece, in the order ``art.py`` has them."""
    if artworks:
        count = len(artworks)
        summary = (
            f"{count} piece{'' if count == 1 else 's'}. Fire "
            "<code>vestaboard_show_art</code> for a random one, or name a piece "
            "in <code>event_data</code> to ask for it."
        )
        cards = "".join(piece(name, artwork) for name, artwork in artworks.items())
    else:
        summary = "Nothing in <code>ARTWORKS</code> yet."
        cards = '<p class="empty">Add a piece to <code>art.py</code> and restart.</p>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Vestaboard art gallery</title>
<style>{STYLE}</style>
</head>
<body>
<header class="top"><div class="inner">
<h1>Art gallery</h1>
<p>{summary}</p>
</div></header>
<main class="gallery">{cards}</main>
</body>
</html>
"""


async def gallery(request: web.Request) -> web.Response:
    """Rendered per request, so a restart is all an edit to ``art.py`` needs."""
    return web.Response(
        text=page(art.ARTWORKS),
        content_type="text/html",
        headers={"Cache-Control": "no-store"},
    )


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", gallery)
    return app


async def serve(port: int) -> web.AppRunner | None:
    """Start the gallery. A port we cannot have is not worth the board over."""
    runner = web.AppRunner(build_app(), access_log=None)
    await runner.setup()
    try:
        await web.TCPSite(runner, HOST, port).start()
    except OSError:
        _LOGGER.exception("art gallery could not listen on port %d", port)
        await runner.cleanup()
        return None

    _LOGGER.info("art gallery listening on port %d", port)
    return runner
