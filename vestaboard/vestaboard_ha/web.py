"""The app's page: the art gallery, and the holidays under review.

The gallery is every piece in ``art.py``, drawn chip for chip.

A card shows the piece itself, at the size it is written: the board's own 15x3
for a full-size piece or a capture, less for a smaller one. The cards are
grouped by category, which is what a rule picks within, so the page reads as
the rotations it is: the art on one heading, the bedtime pieces on another.

Home Assistant serves this page itself, through ingress, so the app appears in
the sidebar with an **Open Web UI** button and nothing is exposed to the network
beyond Supervisor. Ingress mounts us under a path it picks and rewrites per
session, so every URL in the page has to be relative -- easiest to guarantee by
having one route and the stylesheet inline. The two tabs are the same path with
a different query, so the links between them are a query and nothing else.

Outside Home Assistant the same page is on ``ingress_port`` directly, which is
what ``docker-compose.yml`` publishes.

The Capture button posts back to this same path -- ingress rewrites it per
session, so a form with no action of its own is the one that always lands in
the right place -- along with the category to capture into, and the redirect
afterwards is built from the path ingress tells us it is serving us at.

The holidays tab, ``?page=holidays``, is a section per day of what the fetch
wrote down and what Claude made of it, with the household's two say-sos on each
holiday -- the verdict that wins over Claude's, and whether it is an exemplar --
saved as soon as they are changed.
"""

from __future__ import annotations

import html
import json
import logging
import re
from collections.abc import Container, Mapping, Sequence
from datetime import date
from typing import Any
from urllib.parse import urlencode

from aiohttp import web

from . import art, charcodes
from .board import BoardError
from .checkiday import Holiday
from .holidays import HolidayStore, Judgement
from .judge import VERDICTS
from .library import Library

_LOGGER = logging.getLogger(__name__)

#: Ingress reaches us inside the container, so bind everywhere.
HOST = "0.0.0.0"

#: What ingress calls the path it is serving us at, so a redirect can say it.
INGRESS_PATH_HEADER = "X-Ingress-Path"

#: The context the handlers work from, kept on the aiohttp application.
CONTEXT = web.AppKey("context")

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
  --ok: #2f8f52;
  --bad: #c4443f;
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
.top .inner {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px 16px;
}
.titles { flex: 1 1 260px; }
.top h1 {
  margin: 0;
  font-size: 17px;
  letter-spacing: .01em;
}
button {
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  color: var(--page);
  background: var(--ink);
  border: 0;
  border-radius: 8px;
  padding: 9px 14px;
  cursor: pointer;
}
button:hover { opacity: .87; }
button:active { transform: translateY(1px); }
button:focus-visible { outline: 2px solid var(--blue); outline-offset: 2px; }
/* Where a capture lands. It sits against the button it belongs to. */
.capture {
  display: flex;
  align-items: center;
  gap: 8px;
}
select {
  font: inherit;
  font-size: 13px;
  color: var(--ink);
  background: var(--card);
  border: 1px solid var(--edge);
  border-radius: 8px;
  padding: 8px 10px;
}
select:focus-visible { outline: 2px solid var(--blue); outline-offset: 2px; }
/* Delete sits on a card and should not compete with the art. */
.quiet {
  padding: 4px 8px;
  color: var(--muted);
  background: none;
  border: 1px solid var(--edge);
  border-radius: 7px;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: .04em;
}
.quiet:hover {
  opacity: 1;
  color: var(--bad);
  border-color: var(--bad);
}
.remove { margin-left: auto; }
.notice {
  max-width: 720px;
  margin: 16px auto -4px;
  padding: 10px 12px;
  border: 1px solid var(--edge);
  border-left: 3px solid var(--ok);
  border-radius: 8px;
  background: var(--card);
  font-size: 13px;
  line-height: 1.45;
}
.notice.bad { border-left-color: var(--bad); }
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
  gap: 28px;
  max-width: 720px;
  margin: 0 auto;
  padding: 16px 16px 56px;
}
/* One category and the pieces in it. */
.group {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.category {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: .12em;
  text-transform: uppercase;
  color: var(--muted);
}
.piece {
  background: var(--card);
  border: 1px solid var(--edge);
  border-radius: 12px;
  box-shadow: var(--shadow);
  padding: 14px;
}
.name {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--muted);
}
/* Which pieces are files, and so can be renamed or deleted. */
.tag {
  padding: 2px 7px;
  border: 1px solid var(--edge);
  border-radius: 999px;
  font-size: 10px;
  font-weight: 500;
  letter-spacing: .1em;
}
.board {
  container-type: inline-size;
  display: grid;
  grid-template-columns: repeat(var(--cols), 1fr);
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
  font-size: calc(63cqw / var(--cols));
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
/* The heart is a character rather than a colored chip, so it is printed on a
   dark flap like any other -- in red, which is how the board prints it. */
.heart { color: var(--red); }
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
/* The two tabs: the same path, a different query. */
.tabs {
  display: flex;
  gap: 4px;
  margin: 0 0 8px;
}
.tabs a {
  padding: 5px 11px;
  border-radius: 999px;
  color: var(--muted);
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
}
.tabs a:hover { color: var(--ink); }
.tabs a[aria-current="page"] {
  color: var(--page);
  background: var(--ink);
}
.count {
  margin-left: 6px;
  font-weight: 500;
  letter-spacing: .04em;
  text-transform: none;
}
.holiday { padding: 12px 14px; }
/* The one just saved, which the redirect lands on. */
.holiday:target { outline: 2px solid var(--blue); outline-offset: 2px; }
.heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}
.heading h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.3;
}
.heading a { color: inherit; text-decoration: none; }
.heading a:hover { text-decoration: underline; }
.status {
  flex: none;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .04em;
  color: var(--ok);
  border: 1px solid currentColor;
}
.off .status { color: var(--muted); }
.off .heading h3 { color: var(--muted); }
.why {
  margin: 4px 0 10px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.45;
}
.decide {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  font-size: 13px;
}
.decide label {
  display: flex;
  align-items: center;
  gap: 6px;
}
.decide input[type="checkbox"] {
  width: 16px;
  height: 16px;
  margin: 0;
  accent-color: var(--blue);
}
/* Saving happens on change; the button is for a browser that will not. */
.js .decide .save { display: none; }
.more {
  align-self: center;
  color: var(--muted);
  font-size: 13px;
}
"""


def chip(code: int) -> str:
    """One chip of the board: a color, a character, or an unlit flap."""
    color = CHIP_COLORS.get(code)
    if color is not None:
        return f'<span class="chip {color}"></span>'

    if code == charcodes.HEART:
        # The character table has 62 as the degree sign, which is what an older
        # board's flaps carry; ours is a Note, and draws it as a heart.
        return '<span class="chip heart">&#10084;</span>'

    char = charcodes.CODE_TO_CHAR.get(code, " ")
    if char == " ":
        return '<span class="chip"></span>'
    return f'<span class="chip">{html.escape(char)}</span>'


def board(artwork: str, label: str) -> str:
    """An artwork's chips, encoded exactly as they are when the board gets them.

    A piece is as wide as it is -- the board's 15 chips for a full-size piece,
    fewer for a smaller one -- and the card scales to fit it.
    """
    rows = art.rows(artwork)
    chips = "".join(chip(art.encode_chip(cell)) for row in rows for cell in row)
    return (
        f'<div class="board" role="img" style="--cols: {len(rows[0])}" '
        f'aria-label="{html.escape(label)}">{chips}</div>'
    )


def delete_form(name: str) -> str:
    """The Delete button on a saved piece, with an are-you-sure in front of it.

    The confirm is the only script on the page, and the button works without
    it: a browser that ignores it just deletes, which is what was asked for.
    """
    asking = html.escape(f"return confirm({json.dumps(f'Delete {name}?')})")
    return (
        f'<form method="post" class="remove" onsubmit="{asking}">'
        f'<button name="delete" value="{html.escape(name)}" class="quiet">'
        "Delete</button></form>"
    )


def piece(name: str, artwork: art.Piece, *, saved: bool = False) -> str:
    """One card. A piece that no longer encodes says so instead of vanishing."""
    try:
        body = board(artwork.art, f"the {name} artwork")
    except ValueError as exc:
        _LOGGER.warning("artwork %s does not encode: %s", name, exc)
        body = (
            '<p class="broken">This piece does not encode: '
            f"{html.escape(str(exc))}</p>"
        )
    # Only a saved piece can be deleted; the rest are in art.py.
    label = html.escape(name) + ('<span class="tag">saved</span>' if saved else "")
    return (
        '<article class="piece">'
        f'<h3 class="name">{label}{delete_form(name) if saved else ""}</h3>'
        f"{body}</article>"
    )


def group(
    category: str, artworks: Mapping[str, art.Piece], saved: Container[str]
) -> str:
    """One category and its cards, under a heading naming the category.

    The heading is the word an automation sends as ``category``, so the page
    says what to ask for as well as what there is.
    """
    cards = "".join(
        piece(name, artwork, saved=name in saved)
        for name, artwork in artworks.items()
        if artwork.category == category
    )
    if not cards:
        return ""
    return (
        '<section class="group">'
        f'<h2 class="category">{html.escape(category)}</h2>{cards}</section>'
    )


def capture_form(artworks: Mapping[str, art.Piece]) -> str:
    """The header's Capture button, and the category the capture lands in.

    Every category we know is offered, whether or not it has anything in it yet
    -- an empty one is exactly what somebody capturing into it is filling.
    """
    options = "".join(
        f'<option value="{html.escape(category)}"'
        f'{" selected" if category == art.DEFAULT_CATEGORY else ""}>'
        f"{html.escape(category)}</option>"
        for category in art.categories(artworks)
    )
    return (
        '<form method="post" class="capture">'
        f'<label>Into <select name="category">{options}</select></label>'
        '<button name="capture" value="board">Capture the board</button>'
        "</form>"
    )


def page(
    artworks: Mapping[str, art.Piece],
    *,
    saved: Container[str] = (),
    notice: str = "",
    bad_news: bool = False,
) -> str:
    """The whole gallery, a card per piece, grouped by category.

    The categories come in the order ``art.py`` has them, with any a saved piece
    made up itself after them; within a category the pieces keep the order the
    library hands them over in, which is the built-in ones first.
    """
    if artworks:
        count = len(artworks)
        summary = (
            f"{count} piece{'' if count == 1 else 's'}. Fire "
            "<code>vestaboard_show_art</code> for a random one from the "
            "<code>art</code> category, add a <code>category</code> to "
            "<code>event_data</code> to pick within another, or a "
            "<code>name</code> to ask for one piece."
        )
        cards = "".join(
            group(category, artworks, saved) for category in art.categories(artworks)
        )
    else:
        summary = "Nothing in <code>ARTWORKS</code> yet."
        cards = '<p class="empty">Add a piece to <code>art.py</code> and restart.</p>'

    banner = ""
    if notice:
        bad = " bad" if bad_news else ""
        banner = f'<p class="notice{bad}">{html.escape(notice)}</p>'

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
<div class="titles">
{tabs("art")}
<h1>Art gallery</h1>
<p>{summary}</p>
</div>
{capture_form(artworks)}
</div></header>
{banner}
<main class="gallery">{cards}</main>
</body>
</html>
"""


#: The tabs across the top: what each is called, and the query that gets it.
TABS = (("art", "Art", "?"), ("holidays", "Holidays", "?page=holidays"))

#: The query that asks for the holidays tab.
PAGE_KEY = "page"
HOLIDAYS_PAGE = "holidays"


def tabs(current: str) -> str:
    """The links between the tabs. A query alone, so ingress has nothing to break."""
    links = "".join(
        f'<a href="{href}"{' aria-current="page"' if key == current else ""}>'
        f"{label}</a>"
        for key, label, href in TABS
    )
    return f'<nav class="tabs">{links}</nav>'


def show(library: Library, notice: str = "", *, bad_news: bool = False) -> web.Response:
    """The gallery as it stands. Read afresh, so a saved file shows up at once."""
    return web.Response(
        text=page(
            library.pieces(),
            saved=library.saved(),
            notice=notice,
            bad_news=bad_news,
        ),
        content_type="text/html",
        headers={"Cache-Control": "no-store"},
    )


#: How many days the holidays tab shows to begin with, and how many more each
#: press of "Show older days" adds. A year of days is a lot of page.
DAYS_SHOWN = 14
DAYS_KEY = "days"

#: What the category select calls leaving it to Claude.
CLAUDES_CALL = ""


def _days_asked_for(query: Mapping[str, str]) -> int:
    """How many days the page should show, from the query, within reason."""
    raw = str(query.get(DAYS_KEY, ""))
    return int(raw) if raw.isdigit() and 0 < int(raw) <= 10_000 else DAYS_SHOWN


def _anchor(holiday_id: str) -> str:
    return f"h-{holiday_id}"


def describe(judgement: Judgement) -> str:
    """What Claude said, in a sentence, or that it has not said anything yet."""
    if judgement.verdict is None:
        return "Not judged yet."
    said = f"Claude says {judgement.verdict}"
    return f"{said}: {judgement.reason}" if judgement.reason else f"{said}."


def category_select(judgement: Judgement) -> str:
    """The category: Claude's call, or one of the three to override it with."""
    claude = f"Claude's call ({judgement.verdict or 'not judged'})"
    options = [(CLAUDES_CALL, claude)] + [(verdict, verdict) for verdict in VERDICTS]
    chosen = judgement.override or CLAUDES_CALL
    return "".join(
        f'<option value="{value}"{" selected" if value == chosen else ""}>'
        f"{html.escape(label)}</option>"
        for value, label in options
    )


def holiday_card(
    holiday: Holiday, judgement: Judgement, *, judging: bool, days: int
) -> str:
    """One holiday: whether it goes up, why, and the two things to decide.

    The form saves on change, so the select and the box are all there is to
    it; the Save button is for a browser that will not run the one line of
    script that does that.
    """
    up = judgement.goes_up(judging)
    name = html.escape(holiday.name)
    if holiday.url.startswith(("https://", "http://")):
        name = (
            f'<a href="{html.escape(holiday.url)}" target="_blank" '
            f'rel="noopener noreferrer">{name}</a>'
        )
    save = html.escape("this.form.requestSubmit()")
    return (
        f'<article class="piece holiday{"" if up else " off"}" '
        f'id="{_anchor(holiday.id)}">'
        '<div class="heading">'
        f"<h3>{name}</h3>"
        f'<span class="status">{"on the board" if up else "off"}</span>'
        "</div>"
        f'<p class="why">{html.escape(describe(judgement))}</p>'
        '<form method="post" class="decide">'
        f'<input type="hidden" name="holiday" value="{html.escape(holiday.id)}">'
        f'<input type="hidden" name="{DAYS_KEY}" value="{days}">'
        f'<label>Category <select name="override" onchange="{save}">'
        f"{category_select(judgement)}</select></label>"
        '<label><input type="checkbox" name="exemplar" value="yes"'
        f'{" checked" if judgement.exemplar else ""} onchange="{save}"> '
        "Exemplar</label>"
        '<button class="quiet save">Save</button>'
        "</form></article>"
    )


def day_section(
    day: date,
    holidays: Sequence[Holiday],
    judgements: Mapping[str, Judgement],
    *,
    judging: bool,
    days: int,
) -> str:
    """One day's holidays, under a heading saying how many of them go up."""
    up = sum(1 for holiday in holidays if judgements[holiday.id].goes_up(judging))
    cards = "".join(
        holiday_card(holiday, judgements[holiday.id], judging=judging, days=days)
        for holiday in holidays
    )
    return (
        f'<section class="group" id="d-{day.isoformat()}">'
        f'<h2 class="category">{day:%A} {day.day} {day:%B %Y}'
        f'<span class="count">&middot; {up} of {len(holidays)} on the board'
        f"</span></h2>{cards}</section>"
    )


def holidays_page(
    store: HolidayStore,
    *,
    judging: bool,
    days: int = DAYS_SHOWN,
    notice: str = "",
    bad_news: bool = False,
) -> str:
    """The holidays tab: the latest ``days`` days, a section each, newest first.

    A holiday is listed once, under the latest day it fell on: a month-long one
    is on thirty days running, and one set of controls for it is plenty. A day
    whose holidays are all listed under a later one is left out.
    """
    known = store.days()
    shown = list(reversed(known))[:days]
    listed: set[str] = set()
    sections = []
    for day in shown:
        holidays = [h for h in store.holidays_for(day) if h.id not in listed]
        listed.update(holiday.id for holiday in holidays)
        if not holidays:
            continue
        judgements = {holiday.id: store.judgement(holiday.id) for holiday in holidays}
        sections.append(
            day_section(day, holidays, judgements, judging=judging, days=days)
        )

    if len(known) > len(shown):
        sections.append(
            f'<a class="more" href="?page={HOLIDAYS_PAGE}&amp;{DAYS_KEY}='
            f'{days + DAYS_SHOWN}">Show older days</a>'
        )
    if not sections:
        sections.append(
            '<p class="empty">Nothing yet. Fire <code>vestaboard_fetch_holidays'
            "</code> and the day's holidays will be here.</p>"
        )

    if judging:
        summary = (
            "Only holidays that come out as <code>show</code> go on the board. "
            "Pick a category to override Claude, and tick Exemplar to make a "
            "holiday one of the examples Claude learns this house's taste from."
        )
    else:
        summary = (
            "There is no <code>anthropic_api_key</code>, so Claude is not sorting "
            "these and everything goes up unless you pick a category for it."
        )

    banner = ""
    if notice:
        bad = " bad" if bad_news else ""
        banner = f'<p class="notice{bad}">{html.escape(notice)}</p>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Vestaboard holidays</title>
<style>{STYLE}</style>
<script>document.documentElement.classList.add("js")</script>
</head>
<body>
<header class="top"><div class="inner">
<div class="titles">
{tabs(HOLIDAYS_PAGE)}
<h1>Holidays</h1>
<p>{summary}</p>
</div>
</div></header>
{banner}
<main class="gallery">{"".join(sections)}</main>
</body>
</html>
"""


def show_holidays(
    ctx: Any, days: int = DAYS_SHOWN, notice: str = "", *, bad_news: bool = False
) -> web.Response:
    return web.Response(
        text=holidays_page(
            ctx.holidays,
            judging=ctx.judge.configured,
            days=days,
            notice=notice,
            bad_news=bad_news,
        ),
        content_type="text/html",
        headers={"Cache-Control": "no-store"},
    )


#: What a piece can be called, for the names that come back off a redirect.
PIECE_NAME = re.compile(r"[\w.-]{1,64}")


def notice_for(library: Library, query: Mapping[str, str]) -> str:
    """What the redirect after a button press is telling us to say.

    The name has been round the browser: for a piece that should still be here
    that means checking we have it, and for a deleted one, which we will not
    find, that it is at least shaped like one of ours.
    """
    saved = library.saved()
    for key, said in (
        ("saved", "Captured as {} in {}. It is in the rotation now."),
        ("again", "The board is already saved as {} in {}."),
    ):
        name = query.get(key, "")
        if name and name in saved:
            return said.format(name, saved[name].category)

    gone = query.get("deleted", "")
    if gone and PIECE_NAME.fullmatch(gone) and gone not in saved:
        return f"Deleted {gone}."
    return ""


async def gallery(request: web.Request) -> web.Response:
    """Rendered per request, so a restart is all an edit to ``art.py`` needs."""
    ctx = request.app[CONTEXT]
    if request.query.get(PAGE_KEY) == HOLIDAYS_PAGE:
        return show_holidays(ctx, _days_asked_for(request.query))
    return show(ctx.art, notice_for(ctx.art, request.query))


async def posted(request: web.Request) -> web.Response:
    """The buttons. Which one was pressed is in the form, not the path.

    Both answer with a redirect, so that a reload does not press the button a
    second time -- and to the path ingress is serving us at, which only the
    request knows.
    """
    ctx = request.app[CONTEXT]
    form = await request.post()
    if "holiday" in form:
        return await decide(request, ctx, form)
    if "delete" in form:
        return await delete(request, ctx, str(form["delete"]))
    return await capture(request, ctx, str(form.get("category", "")))


async def capture(request: web.Request, ctx: Any, category: str = "") -> web.Response:
    """Save what is on the board right now as a new piece in that category."""
    try:
        saved = ctx.art.capture(await ctx.board.read(), category)
    except (BoardError, ValueError, OSError) as exc:
        _LOGGER.warning("could not capture the board: %s", exc)
        return show(ctx.art, f"Could not capture the board: {exc}", bad_news=True)

    key = "saved" if saved.is_new else "again"
    raise web.HTTPSeeOther(f"{_base_path(request)}/?{urlencode({key: saved.name})}")


async def delete(request: web.Request, ctx: Any, name: str) -> web.Response:
    """Throw a saved piece away."""
    try:
        ctx.art.delete(name)
    except (ValueError, OSError) as exc:
        _LOGGER.warning("could not delete %s: %s", name, exc)
        return show(ctx.art, f"Could not delete it: {exc}", bad_news=True)

    raise web.HTTPSeeOther(f"{_base_path(request)}/?{urlencode({'deleted': name})}")


async def decide(request: web.Request, ctx: Any, form: Mapping[str, Any]) -> web.Response:
    """Save what was picked for one holiday, and go back to where it is.

    The form is the whole of the decision -- an unticked box is not sent at
    all -- so a holiday's override and exemplar are both written every time.
    """
    holiday_id = str(form.get("holiday", ""))
    override = str(form.get("override", CLAUDES_CALL)) or None
    exemplar = "exemplar" in form
    days = _days_asked_for(form)
    try:
        ctx.holidays.decide(holiday_id, override, exemplar)
    except (ValueError, OSError) as exc:
        _LOGGER.warning("could not save holiday %s: %s", holiday_id, exc)
        return show_holidays(ctx, days, f"Could not save that: {exc}", bad_news=True)

    _LOGGER.info(
        "holidays: %s is now %s%s",
        holiday_id,
        override or "Claude's call",
        ", an exemplar" if exemplar else "",
    )
    query = urlencode({PAGE_KEY: HOLIDAYS_PAGE, DAYS_KEY: days})
    raise web.HTTPSeeOther(f"{_base_path(request)}/?{query}#{_anchor(holiday_id)}")


def _base_path(request: web.Request) -> str:
    """The path the page is being served at, as far as the browser is concerned."""
    path = request.headers.get(INGRESS_PATH_HEADER, "")
    # Ingress sets this, but a redirect is worth being careful with: anything
    # that is not a path of ours leaves us redirecting to our own root.
    if not path.startswith("/") or path.startswith("//"):
        return ""
    return path.rstrip("/")


def build_app(ctx: Any) -> web.Application:
    app = web.Application()
    app[CONTEXT] = ctx
    app.router.add_get("/", gallery)
    app.router.add_post("/", posted)
    return app


async def serve(ctx: Any, port: int) -> web.AppRunner | None:
    """Start the gallery. A port we cannot have is not worth the board over."""
    runner = web.AppRunner(build_app(ctx), access_log=None)
    await runner.setup()
    try:
        await web.TCPSite(runner, HOST, port).start()
    except OSError:
        _LOGGER.exception("art gallery could not listen on port %d", port)
        await runner.cleanup()
        return None

    _LOGGER.info("art gallery listening on port %d", port)
    return runner
