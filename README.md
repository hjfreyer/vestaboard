# vestaboard

Puts my Vestaboard in Home Assistant as a device: a channel to tune it to, a
message to give it, and the events it always answered to. Built for my house
specifically; you are welcome to steal from it.

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
7. For the device, install the **Mosquitto broker** app from the same store
   and the **MQTT** integration under **Settings → Devices & services**, if
   you have not already. Nothing to configure here: Supervisor tells the app
   where the broker is, and the **Vestaboard** device appears under MQTT the
   next time the app starts.

Set `dry_run: true` in the configuration first if you want to see what it would
send before letting it touch the board. Without a broker the app runs as it
always has, on events alone, and says so in the log.

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
    device.py              the board as Home Assistant sees it: the controls
    mqtt.py                the connection the device is announced over
    app.py                 wires rules to Home Assistant: events and the device
    registry.py            the @channel and @on_action decorators
    board.py               Vestaboard Cloud API client
    hass.py                Home Assistant websocket + REST client
    supervisor.py          asks Supervisor for the broker, and who we are
    charcodes.py           character codes, for exact placement
    settings.py            app options, or env vars outside Home Assistant
  tests/
docker-compose.yml         fallback for installs without the app store
```

## The device

Home Assistant sees the board as a device called **Vestaboard**, under the
MQTT integration, with these on it:

| Entity                                | What it is                                                     |
| ------------------------------------- | -------------------------------------------------------------- |
| `select.vestaboard_channel`           | What the board shows: **Hold**, **Art**, **Message** or **Eggs**. |
| `select.vestaboard_piece`             | Which piece the Art channel shows: a name, or **Random**.      |
| `number.vestaboard_art_rotation`      | Minutes between random pieces. 0 keeps the one that is up.     |
| `text.vestaboard_message`             | What the Message channel says. Empty clears the board.         |
| `button.vestaboard_next_piece`        | Another random piece, on the Art channel.                      |
| `button.vestaboard_capture_the_board` | Saves what is on the board to the gallery.                     |
| `sensor.vestaboard_showing`           | What is on the board, in a few words.                          |

The board shows the channel, and only the channel. Change the channel and it
redraws; change a control the channel draws from -- the piece, the message --
and it redraws; otherwise nothing touches it. **Hold** is the channel that
draws nothing, for a board somebody has written on by hand, and the one a
fresh install starts on, so installing this changes nothing until you pick.

A schedule, then, is an automation on the select, like any other select:

```yaml
alias: Eggs in the morning
triggers:
  - trigger: time
    at: "07:00:00"
actions:
  - action: select.select_option
    target:
      entity_id: select.vestaboard_channel
    data:
      option: Eggs
```

A message is the text entity, with a template if it wants one, and then the
channel:

```yaml
actions:
  - action: text.set_value
    target:
      entity_id: text.vestaboard_message
    data:
      value: "{{ states('sensor.outside_temperature') | round }} DEGREES"
  - action: select.select_option
    target:
      entity_id: select.vestaboard_channel
    data:
      option: Message
```

The events are still there, and each is the two steps in one: the remote
control. `vestaboard_text` sets the message and tunes to Message;
`vestaboard_show_art` sets the piece, or Random, and tunes to Art;
`vestaboard_eggs` keeps its numbers and tunes to Eggs. Whichever way the board
was changed, the Channel select reads what it is showing.

The device's state -- the channel, the piece, the message, the last egg
numbers -- is kept in `/data/device.json`, so a restart comes back on the same
channel. Home Assistant is where it is changed; the file is only so the app
remembers. When the app is down the device shows as unavailable rather than
stale, and comes back when it does.

## Writing rules

```python
@channel("dinner", label="Dinner")
async def dinner(ctx):
    await ctx.board.send_text("DINNER")
    return "DINNER"


@on_action("dinner")
async def dinner_time(ctx, data):
    await ctx.device.tune("dinner")
```

There are two kinds of rule. A `@channel` is something the board can be tuned
to: its function draws the board from the device's controls -- `ctx.device.piece`,
`ctx.device.message`, `ctx.device.data_for("eggs")` -- and returns a word or two
on what it drew, for the Showing sensor. Every channel is an option on the
Channel select, in the order declared. `uses=("piece",)` names the controls a
channel draws from, so a change to one of them in Home Assistant redraws the
channel that is up and leaves the others alone; and a channel that wants to
change on its own, as the art does, asks with `ctx.device.redraw_in(seconds)`
from inside its own drawing.

An `@on_action` runs when Home Assistant fires the matching event, and is the
remote control: it sets a control or two and tunes. An app cannot register a
real action (what Home Assistant called a service before the rename), so an
action here is a custom event under our own name -- `@on_action("show_art")`
runs whenever anything fires `vestaboard_show_art` -- and the rule is handed
the event data as its second argument. In the automation editor that is
**Add action → Other actions → Fire event**.

Either way Home Assistant decides when. Dinner at half five is an automation
on the select, or on the event, and not a rule:

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

`vestaboard_text` is the plainest of the actions shipped: it makes the `text`
it is given the device's Message and tunes to it, laid out by the board itself,
so an automation with a template can say something new without a push here.

```yaml
actions:
  - event: vestaboard_text
    event_data:
      text: "{{ states('sensor.outside_temperature') | round }} DEGREES"
```

An event with no `text`, or nothing but spaces, is logged and leaves the board
and the Message alone; the Cloud API does not take a blank message. Setting the
text entity itself to nothing is different: that clears the board, as a grid
of blank chips, which the Cloud API does take.

`vestaboard_eggs` is the other action shipped, and shows what a rule can build:
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
rather than four; a day's eggs need fewer. The numbers are kept, so tuning to
Eggs from the device page later shows the last ones sent, under a fresh hen.

`ctx.board` sends to the board, `ctx.hass` reads state and calls services,
`ctx.device` is the device's controls and `ctx.device.tune(...)` the dial, and
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

The rotation is the device's: with the Channel on **Art** and the Piece on
**Random**, the board changes every **Art rotation** minutes, never to the
piece already up. It starts at 30; set it on the device page, or from an
automation with `number.set_value`, and 0 keeps the piece that is up. Nothing
to push either way. If you had the half-hourly `vestaboard_show_art`
automation from before this was a device, delete it: firing that event tunes
to Art, which every half hour is not what a schedule wants.

To hold a particular piece, pick it on the **Piece** select, or name it in the
event, which does the same and tunes to Art:

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
  STATE_PATH=./device.json python -m vestaboard_ha
```

`HASS_TOKEN` is a long-lived access token from your Home Assistant profile
page. Add `MQTT_HOST`, and `MQTT_USERNAME` and `MQTT_PASSWORD` if the broker
wants them, to put the device on a broker from here -- it will take over from
the app's copy, which connects under the same name. Inside the app none of
this is needed.
