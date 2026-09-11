# vestaboard

Pushes messages to my Vestaboard, on a schedule and in response to Home
Assistant events. Built for my house specifically; you are welcome to steal
from it.

This repository is a **Home Assistant app repository** (what Home Assistant
called an add-on repository before the 2026 rename). Home Assistant installs
the app from GitHub and offers an Update button when I push.

The rename was UI strings only: the files here are still `repository.yaml` and
`config.yaml`, the folder is still the add-on slug, and Supervisor still builds
it the same way.

## Installing

1. In Home Assistant, go to **Settings → Apps → App store**.
2. Three-dot menu (top right) → **Repositories**.
3. Add `https://github.com/hjfreyer/vestaboard` and close the dialog.
4. The **Vestaboard** app appears at the bottom of the store. Install it.
5. On its **Configuration** tab, paste a Vestaboard Cloud API token, which
   you create in the Developer section of the Vestaboard web app.
6. Start it, and watch the **Log** tab.

Set `dry_run: true` in the configuration first if you want to see what it would
send before letting it touch the board.

## Updating

1. Edit `vestaboard/vestaboard_ha/rules.py` and push to `main`.
2. CI bumps the version number in `config.yaml`, which is what makes Home
   Assistant notice there is something new.
3. In Home Assistant, open the app and press **Update**. (Supervisor checks the
   repository every so often; the store's three-dot **Check for updates**
   forces it.)

Nothing to SSH into, and a broken push does not reach the board until the
Update button is pressed.

## Layout

```
repository.yaml            marks this repo as an app repository
vestaboard/                the app; also the Docker build context
  config.yaml              app manifest, including the version number
  Dockerfile               how Supervisor builds it
  vestaboard_ha/
    rules.py               >>> the file worth editing <<<
    art.py                 the pixel art, and the encoding of it
    library.py             the art on disk, capturing it, and picking one
    web.py                 the art gallery, served over ingress
    app.py                 wires rules to the scheduler and the event stream
    registry.py            the @on_schedule, @on_state and @on_action decorators
    board.py               Vestaboard Cloud API client
    hass.py                Home Assistant websocket + REST client
    charcodes.py           character codes, for exact placement
    settings.py            app options, or env vars outside Home Assistant
  tests/
docker-compose.yml         fallback for installs without the app store
```

## Writing rules

```python
@on_schedule(hour=17, minute=30)
async def dinner_time(ctx):
    await ctx.board.send_text("DINNER")


@on_state("counter.eggs")
async def eggs_changed(ctx, event):
    await ctx.board.send_text(f"EGGS: {event['new_state']['state']}")


@on_action("show_art")
async def show_art(ctx, data):
    await ctx.board.send_characters(ctx.art.grid(data.get("name")))
```

`@on_state` fires only when the value really changes, so a rule can read
`event["new_state"]["state"]` without checking it first. Attribute-only edits,
the restore that follows a Home Assistant restart, and values going `unknown`
or `unavailable` all pass by silently -- unless `to=` or `from_=` asks for one
of those states by name.

`@on_action` is the other direction: Home Assistant decides when. An app cannot
register a real action (what Home Assistant called a service before the
rename), so an action here is a custom event under our own name --
`@on_action("show_art")` runs whenever anything fires `vestaboard_show_art` --
and the rule is handed the event data as its second argument. In the automation
editor that is **Add action → Other actions → Fire event**.

`ctx.board` sends to the board, `ctx.hass` reads state and calls services, and
`ctx.art` is the art library: `ctx.art.grid("heart")` for a named piece,
`ctx.art.grid()` for a random one.
Schedules use APScheduler's cron fields in the container's timezone, which
Home Assistant sets to match the one configured for the house.

## Pixel art

The board is a Vestaboard Note: 15 chips across, 3 rows down, which is what a
piece is. `art.py` holds the artwork, written inline so the source shows it:

```python
ARTWORKS = {
    "sunset": """
⬛⬛⬛⬛⬛⬛🟨🟨🟨⬛⬛⬛⬛⬛⬛
⬛⬛⬛🟨🟨🟧🟧🟧🟧🟧🟨🟨⬛⬛⬛
🟧🟧🟧🟧🟥🟥🟥🟥🟥🟥🟥🟧🟧🟧🟧
""",
}
```

The squares are `🟥 🟧 🟨 🟩 🟦 🟪 ⬜`, and `⬛` is a blank chip -- the board's
black chip looks no different, so there is only the one square for both.

Every chip is two columns wide, because that is what a fixed-width font gives a
colored square, and text has to keep to the same grid: **a character is written
as a space and then the character.** So ` P A R T Y` is five chips, not ten,
a bare `PARTY` is an error, and two spaces are a blank chip. That is what lets
a piece mix the two:

```python
    "party": """
🟥🟧🟨🟩🟦🟪🟥🟧🟨🟩🟦🟪🟥🟧🟨
⬛⬛⬛⬛ P A R T Y !⬛⬛⬛⬛⬛
🟪🟦🟩🟨🟧🟥🟪🟦🟩🟨🟧🟥🟪🟦🟩
""",
```

Lines are written flush left and may stop early; the right side is padded with
blanks, and a piece smaller than the board is centered on it.

### Saved art

Pieces also come from files. `/data/art` is part of the app's own storage, so
it survives restarts and updates, and every `.txt` file in it is a piece named
after the file -- `sunrise.txt` is `sunrise`, written in the same squares as
`art.py`. Delete the file and the piece is gone; rename it and the piece is
renamed. A file wins over a piece of the same name in `art.py`, because a file
is something you put there on purpose.

The gallery's **Capture the board** button is the quick way to make one: it
reads what the board is showing right now and writes it to the next free
`capture-N.txt`, text and all. Capturing the same thing twice does not make a
second file. A saved piece is in the rotation from that moment, without a
restart.

A file that no longer parses -- an easy thing to do by hand -- says so on its
card in the gallery and sits out the rotation, rather than breaking either.

### The gallery

Every piece, chip for chip, is on the app's own page: **Open Web UI** on the app
in Home Assistant, or the sidebar entry if you turn one on from that page. It is
a scrollable list, one card per piece, labeled with the name to pass as
`event_data` and marked `saved` when the piece is a file rather than something
in `art.py`. There is a **Capture the board** button in the header.

The page is built on each request, so a saved piece appears the moment it is
written and a piece added to `art.py` appears as soon as the app restarts.

Home Assistant serves the page itself, through ingress, so nothing is exposed
to the network and there is no port to open. Outside the app store the same
page is at `http://localhost:8099/`, which `docker-compose.yml` publishes.

The rotation lives in Home Assistant rather than here, so it can be changed
without pushing anything:

```yaml
alias: Vestaboard art
triggers:
  - trigger: time_pattern
    minutes: "/30"
actions:
  - event: vestaboard_show_art
```

That is a random piece every half hour, never the same one twice in a row. To
ask for a particular one, name it:

```yaml
actions:
  - event: vestaboard_show_art
    event_data:
      name: heart
```

## Developing locally

```
cd vestaboard
pip install -r requirements-dev.txt
pytest
ruff check .

# Run against the real Home Assistant without touching the board:
DRY_RUN=true HASS_URL=http://homeassistant.local:8123 HASS_TOKEN=... \
  python -m vestaboard_ha
```

`HASS_TOKEN` is a long-lived access token from your Home Assistant profile
page. Inside the app none of this is needed.
