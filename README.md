# vestaboard

Pushes messages to my Vestaboard in response to Home Assistant events. Built
for my house specifically; you are welcome to steal from it.

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
    app.py                 wires rules to the Home Assistant event stream
    registry.py            the @on_action decorator
    board.py               Vestaboard Cloud API client
    hass.py                Home Assistant websocket + REST client
    charcodes.py           character codes, for exact placement
    settings.py            app options, or env vars outside Home Assistant
  tests/
docker-compose.yml         fallback for installs without the app store
```

## Writing rules

```python
@on_action("dinner")
async def dinner_time(ctx, data):
    await ctx.board.send_text("DINNER")


@on_action("show_art")
async def show_art(ctx, data):
    await ctx.board.send_characters(ctx.art.grid(data.get("name")))
```

`@on_action` is the only way a rule runs, and Home Assistant decides when. An
app cannot register a real action (what Home Assistant called a service before
the rename), so an action here is a custom event under our own name --
`@on_action("show_art")` runs whenever anything fires `vestaboard_show_art` --
and the rule is handed the event data as its second argument. In the automation
editor that is **Add action → Other actions → Fire event**.

Dinner at half five, then, is an automation and not a rule:

```yaml
alias: Dinner
triggers:
  - trigger: time
    at: "17:30:00"
actions:
  - event: vestaboard_dinner
```

That is deliberate. Home Assistant already knows how to trigger on a clock, on
an entity changing, on the sun going down, and it can be edited without pushing
anything; a rule that ran itself would only be a second place to look.

`vestaboard_text` is the plainest of the actions shipped: it puts the `text` it
is given on the board, laid out by the board itself, so an automation with a
template can say something new without a push here.

```yaml
actions:
  - event: vestaboard_text
    event_data:
      text: "{{ states('sensor.outside_temperature') | round }} DEGREES"
```

An event with no `text`, or nothing but spaces, is logged and leaves the board
alone; the Cloud API does not take a blank message.

`vestaboard_eggs` is one of the two actions that show what a rule can build:
a hen in the seven chips on the left, `TODAY`, `MTD` and `YTD` down the middle,
and a number against the right edge of each row. `today` is a count of eggs;
`mtd` and `ytd` are eggs per day so far this month and this year. The hen is
one of the `CHICKENS` in `rules.py`, picked at random, so add another there and
it joins the rotation -- three rows of seven chips, blanks written out to the
last one.

```yaml
actions:
  - event: vestaboard_eggs
    event_data:
      today: 3
      mtd: 2.75
      ytd: 2.41
```

The automation is what knows the numbers; `rules.py` only lays them out. Each
keeps as many decimals as fit in the chips its row has left it -- `2.75` under
ten, `12.3` over it, `999+` past the end -- and a number that is missing or is
not a number at all shows as `?` rather than costing the board the other two.
`TODAY` is two letters longer than the other labels, so it leaves three chips
rather than four; a day's eggs need fewer.

`vestaboard_smoker` is the other, and is the one with a row that comes and
goes: smoke in the three chips on the left, `FOOD` and `AIR` for the probe in
the meat and the smoker itself, and a `TIMER` counting down underneath -- but
only when the automation sent a `duration` to count.

```yaml
actions:
  - event: vestaboard_smoker
    event_data:
      food: 135
      air: 227
      duration: "2:06:33"
```

```
⬜⬜⬛⬛⬛⬛ F O O D⬛ 1 3 5 F
⬛⬜⬜⬛⬛⬛⬛ A I R⬛ 2 2 7 F
⬛⬛🟥⬛⬛ T I M E R⬛ 2 : 0 6
```

The duration is seconds as a number, or `H:MM:SS` or `H:MM` as a string, which
is the form a timer entity's `remaining` comes in; seconds are dropped rather
than rounded, the way a countdown reads. Leave it out -- or template it so it
renders to nothing while nothing is cooking -- and the TIMER row is not on the
board at all, though the ember keeps its corner. Temperatures go up as whole
degrees and an `F`, which is doing the job a degree sign would: code 62 is a
degree sign on the flagship board and a red heart on this one. A reading that
is missing or is not a number shows as `?` rather than costing the board the
others, and a cook past ten hours takes the chip its `12:06` needs from every
row at once, so the readings stay in a column.

`ctx.board` sends to the board, `ctx.hass` reads state and calls services, and
`ctx.art` is the art library: `ctx.art.grid("rainbow")` for a named piece,
`ctx.art.grid()` for a random one.

## Pixel art

The board is a Vestaboard Note: 15 chips across, 3 rows down, which is what a
piece is. `art.py` holds the artwork, written inline so the source shows it:

```python
ARTWORKS = {
    "rainbow": """
🟥🟥🟥🟧🟧🟧🟨🟨🟨🟩🟩🟩🟦🟦🟦
🟧🟧🟧🟨🟨🟨🟩🟩🟩🟦🟦🟦🟪🟪🟪
🟨🟨🟨🟩🟩🟩🟦🟦🟦🟪🟪🟪🟥🟥🟥
""",
}
```

The squares are `🟥 🟧 🟨 🟩 🟦 🟪 ⬜ ❤️`, and `⬛` is a blank chip -- the board's
black chip looks no different, so there is only the one square for both. The
heart is not a color at all: it is character code 62. That is one flap with
two meanings -- a degree sign on the flagship board, a red heart on a Note --
and this board is a Note, so a heart is what it shows. Either spelling can be
written; a heart is what comes back.

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

`art.py` ships with `rainbow` and nothing else; everything past that is yours
to write, or to capture.

Lines are written flush left and may stop early; the right side is padded with
blanks, and a piece smaller than the board is centered on it.

### Saved art

Pieces also come from files. `/data/art` is part of the app's own storage, so
it survives restarts and updates, and every `.txt` file in it is a piece named
after the file -- `sunrise.txt` is `sunrise`, written in the same squares as
`art.py`. Delete the file and the piece is gone -- which is what **Delete** on
a card in the gallery does, after asking -- and rename it and the piece is
renamed. Only saved pieces have the button; anything in `art.py` is deleted by
editing `art.py`. A file wins over a piece of the same name in `art.py`, because a file
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
      name: rainbow
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
