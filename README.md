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
    art.py                 the pixel art, its categories, and the encoding
    library.py             the art on disk, capturing it, and picking one
    web.py                 the art gallery, served over ingress
    app.py                 wires rules to the Home Assistant event stream
    registry.py            the @on_action decorator
    board.py               Vestaboard Cloud API client
    hass.py                Home Assistant websocket + REST client
    checkiday.py           Checkiday API client: a date's holidays
    holidays.py            the holidays on disk: a day's ids, and what they mean
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

`vestaboard_forecast` is the third: the date down the left, the day's weather
drawn in the middle, and its high over its low on the right, each said in
Fahrenheit and in Celsius.

```yaml
alias: Vestaboard forecast
triggers:
  - trigger: time
    at: "06:45:00"
actions:
  - action: weather.get_forecasts
    target:
      entity_id: weather.home
    data:
      type: daily
    response_variable: forecasts
  - event: vestaboard_forecast
    event_data:
      condition: "{{ forecasts['weather.home'].forecast[0].condition }}"
      high: "{{ forecasts['weather.home'].forecast[0].temperature }}"
      low: "{{ forecasts['weather.home'].forecast[0].templow }}"
```

```
 S U N⬛⬛⬜⬜⬛⬛⬛ 7 0⬛ 2 1
 S E P⬛⬜⬜⬜⬜⬛⬛ 4 8⬛⬛ 9
 2 0⬛⬛ :⬛ :⬛⬛⬛⬛ F⬛⬛ C
```

`weather.get_forecasts` is how Home Assistant hands out a forecast, and its
daily entries are exactly what the three keys above take: `condition`, and
`temperature` and `templow` for the day's high and low. Those names work too,
so the fields can be copied off an entry under either one.

A forecast comes in whichever unit Home Assistant is set to, which is Celsius
unless that is US customary -- so the temperatures are read as Celsius unless
the automation says otherwise, and the weather entity knows its own answer:

```yaml
    event_data:
      unit: "{{ state_attr('weather.home', 'temperature_unit') }}"
      condition: "{{ forecasts['weather.home'].forecast[0].condition }}"
      high: "{{ forecasts['weather.home'].forecast[0].temperature }}"
      low: "{{ forecasts['weather.home'].forecast[0].templow }}"
```

That renders to `°C` or `°F`, both of which this takes, as it does a plain `C`
or `F`; `temperature_unit` works as a key name as well as `unit`. Whichever
unit comes in, both columns go up -- the other one is worked out here. A
temperature that is missing or is not one shows as `?` in both columns, and
each column is as wide as the widest reading in it, so an
ordinary `21`C leaves the chip a `-11`C would have taken to the middle of the
board. Three chips is as wide as a column gets, which is a `100`F afternoon
and a `-20`C morning both.

`condition` is one of the fifteen a Home Assistant weather entity can report,
and `rules.py` draws every one of them in the four chips in the middle:
`clear-night`, `cloudy`, `exceptional`, `fog`, `hail`, `lightning`,
`lightning-rainy`, `partlycloudy`, `pouring`, `rainy`, `snowy`, `snowy-rainy`,
`sunny`, `windy` and `windy-variant`. They are the `FORECASTS` in `rules.py`,
written out in the same squares as `art.py`: the same pyramid of a cloud
wherever a cloud appears, with what falls out of it written as characters --
`:` for rain, `/` for a downpour, `#` for snow, `O` for hail -- since a white
chip under a white cloud reads as more cloud rather than as falling. What four
chips across cannot tell apart -- a gust from a variant gust, a clear day from
a clear night -- is drawn alike on purpose. A condition we do not know, or none
at all, draws a `?` and says so in the log rather than putting up sunshine.

The date is the app's own, which is Home Assistant's timezone -- Supervisor
sets the container's clock to it. Send a `date` in the `event_data` (an ISO
date, or a forecast's own `datetime`) to say otherwise.

`vestaboard_fetch_holidays` is the odd one out: it puts nothing on the board at
all. It asks [Checkiday](https://www.checkiday.com/) which of its several
thousand holidays fall today -- the national days, the awareness months, and
the properly obscure ones -- and writes down what it hears, so that something
later can make a board out of it.

```yaml
alias: Vestaboard holidays
triggers:
  - trigger: time
    at: "06:30:00"
actions:
  - event: vestaboard_fetch_holidays
```

The key goes in `checkiday_api_key` on the app's **Configuration** tab; you
make one in the [Checkiday API's](https://apilayer.com/marketplace/checkiday-api)
own dashboard. Without one the rule says so at startup and leaves everything
alone, which is what an install that does not want holidays looks like.

A free key is a hundred requests a month, which is the whole reason for the
caches below: one ask a day is thirty of them, and everything else is margin.

What a request is allowed to say is sold separately from how many of them you
get. Asking about a particular date wants a Pro plan, and naming the timezone
that date is reckoned in wants an Enterprise one, so this asks for neither: the
question is only ever "what is today", and the answer says which day Checkiday
decided that was. Below an Enterprise plan that day is worked out in
`America/Chicago` rather than wherever you are, which is why it is read off the
answer instead of taken from our own clock -- and why the automation above
fires in the morning, the part of the day the two agree about.

What it writes is two caches under `/data/holidays`, which is the app's own
storage and so survives restarts and updates:

```
/data/holidays/
  days/2026-09-22.json      the ids of that date's holidays
  events/676cd91e...json    what one id means: its name, its page, its length
```

They are two things because they go stale at completely different rates. A day
is asked about once and written once -- firing the event again on a day already
written costs nothing, which is what stops an automation on a time pattern from
spending the month's requests before lunchtime -- while a holiday comes round
every year, so its name is worth keeping for good and worth asking for once. A
year of days is therefore a year of holidays whose names we already have.

Both are plain JSON, so the lot can be read, corrected or thrown away with a
text editor. A file that will not parse counts as one that is not there, which
means the next fetch simply fills it in again.

To go back and ask about a day already written -- a holiday added to Checkiday
during the day, most likely:

```yaml
actions:
  - event: vestaboard_fetch_holidays
    event_data:
      refresh: true
```

An ask that goes wrong spends a request the same as one that works, so a day
that has failed three times is left until tomorrow rather than retried all
afternoon. The log says when that happens, and `refresh: true` tries it anyway
-- which is the thing to fire once you have fixed whatever was wrong.

There is nothing else to send: a `date` in the `event_data` is not asked for,
since asking for one is the Pro plan's to do.

`vestaboard_show_holiday` is what puts one on the board. It reads what the
fetch wrote down, picks one of the day's holidays at random, and lays the name
out:

```yaml
alias: Vestaboard holiday
triggers:
  - trigger: time_pattern
    hours: "/2"
actions:
  - event: vestaboard_show_holiday
```

Nothing is asked of Checkiday here, so this is free to fire as often as you
like: it only ever reads the day the fetch already paid for. A day nobody
fetched, and a day that turned out to hold no holidays, are both logged and
leave the board showing whatever it had.

Fifteen chips across and three down is not much room for a name like
International Day for the Preservation of the Ozone Layer, so a name that will
not go on is shortened a step at a time, and no further than it has to be.
First the scope is written short -- `NATIONAL` becomes `NAT'L` and
`INTERNATIONAL` becomes `INT'L` -- then it is dropped altogether, and only if
it still will not go are the words that are left over replaced with dots:

```
National Chicken Month           NATIONAL
                                 CHICKEN MONTH

International Day of Persons     INT'L DAY OF
with Disabilities                PERSONS WITH
                                 DISABILITIES

International Day for the        DAY FOR THE
Preservation of the Ozone        PRESERVATION OF
Layer                            THE OZONE LAYER

International Day for the        DAY FOR THE
Total Elimination of Nuclear     TOTAL
Weapons                          ELIMINATION...
```

`WORLD` is already as short as it goes, so it comes through the first step
unchanged and goes at the second. A holiday whose whole name is its scope keeps
it, since a blank board is worse than one that overreaches. Names are wrapped
at the spaces and nowhere else, and the one word too long for a row on its own
is cut where it runs out.

Checkiday writes for a web page, so a name can arrive with a curly apostrophe,
an en dash or an accent in it. Those are spelled the plain way the board has
flaps for, and anything still unsayable becomes a space rather than an error --
one strange character should cost that character and not the whole board.

`ctx.board` sends to the board, `ctx.hass` reads state and calls services, and
`ctx.art` is the art library: `ctx.art.grid("rainbow")` for a named piece,
`ctx.art.grid()` for a random one from the `art` category, and
`ctx.art.grid(category="bedtime")` for a random one from another.
`ctx.checkiday` asks Checkiday about a date, and `ctx.holidays` is where the
answers are kept: `ctx.holidays.holidays_for(day)` for a day's holidays with
their names on, and `ctx.holidays.ids_for(day)` to tell a day with nothing on
it from a day nobody has asked about yet.

## Pixel art

The board is a Vestaboard Note: 15 chips across, 3 rows down, which is what a
piece is. `art.py` holds the artwork, written inline so the source shows it:

```python
ARTWORKS = {
    "rainbow": Piece("""
🟥🟥🟥🟧🟧🟧🟨🟨🟨🟩🟩🟩🟦🟦🟦
🟧🟧🟧🟨🟨🟨🟩🟩🟩🟦🟦🟦🟪🟪🟪
🟨🟨🟨🟩🟩🟩🟦🟦🟦🟪🟪🟪🟥🟥🟥
"""),
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
    "party": Piece("""
🟥🟧🟨🟩🟦🟪🟥🟧🟨🟩🟦🟪🟥🟧🟨
⬛⬛⬛⬛ P A R T Y !⬛⬛⬛⬛⬛
🟪🟦🟩🟨🟧🟥🟪🟦🟩🟨🟧🟥🟪🟦🟩
"""),
```

`art.py` ships with `rainbow` and `zzz` and nothing else; everything past that
is yours to write, or to capture.

Lines are written flush left and may stop early; the right side is padded with
blanks, and a piece smaller than the board is centered on it.

### Categories

A piece belongs to a category, and a random pick is made within one, so the
board has as many rotations as you give it categories. `art` is the category a
piece is in when it does not say otherwise, and `bedtime` is the other one
shipped -- the quiet pieces, which the daytime rotation should not reach for:

```python
    "zzz": Piece("""
 Z Z Z Z Z Z Z Z Z Z Z Z Z Z Z
 Z Z Z Z Z Z Z Z Z Z Z Z Z Z Z
 Z Z Z Z Z Z Z Z Z Z Z Z Z Z Z
""", category="bedtime"),
```

Nothing stops a piece naming a category of its own -- `smoker`, say, for the
boards a cook wants -- and the gallery and the event take it from there. The
categories in `CATEGORIES` are the ones the gallery offers to capture into;
the rest are made by putting a piece in one.

### Saved art

Pieces also come from files. `/data/art` is part of the app's own storage, so
it survives restarts and updates, and every `.txt` file in it is a piece named
after the file -- `sunrise.txt` is `sunrise`, written in the same squares as
`art.py`. Delete the file and the piece is gone -- which is what **Delete** on
a card in the gallery does, after asking -- and rename it and the piece is
renamed. Only saved pieces have the button; anything in `art.py` is deleted by
editing `art.py`. A file wins over a piece of the same name in `art.py`, because a file
is something you put there on purpose.

A directory is a category: `/data/art/bedtime/moonrise.txt` is `moonrise` in
the `bedtime` category, and a file in `/data/art` itself is in `art`. Moving a
file between them is how a saved piece changes category, the same way renaming
it is how a piece is renamed. A name is a name wherever its file sits, so two
files of the same name in different categories are one piece and the one at the
top level wins.

The gallery's **Capture the board** button is the quick way to make one: it
reads what the board is showing right now and writes it to the next free
`capture-N.txt`, text and all, in whichever category the **Into** menu beside
it says. Capturing the same thing into the same category twice does not make a
second file -- into another category it does, since those are two pieces shown
at different times of day. A saved piece is in the rotation from that moment,
without a restart.

A file that no longer parses -- an easy thing to do by hand -- says so on its
card in the gallery and sits out the rotation, rather than breaking either.

### The gallery

Every piece, chip for chip, is on the app's own page: **Open Web UI** on the app
in Home Assistant, or the sidebar entry if you turn one on from that page. It is
a scrollable list, one card per piece, labeled with the name to pass as
`event_data` and marked `saved` when the piece is a file rather than something
in `art.py`. The cards are grouped under the category to pass as `category`, so
the page reads as the rotations it is. There is a **Capture the board** button
in the header, and a menu beside it for which category the capture lands in.

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

That is a random `art` piece every half hour, never the same one twice in a
row. A second automation, firing once at bedtime, is the other rotation:

```yaml
alias: Vestaboard bedtime
triggers:
  - trigger: time
    at: "20:30:00"
actions:
  - event: vestaboard_show_art
    event_data:
      category: bedtime
```

To ask for a particular piece, name it -- a name is a name whichever category
the piece is in:

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
page, and `CHECKIDAY_API_KEY` is the holiday key outside the app store, the way
`VESTABOARD_API_TOKEN` is the board's. Inside the app none of this is needed.
