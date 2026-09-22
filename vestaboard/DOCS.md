# Vestaboard

Pushes messages to my Vestaboard in response to Home Assistant events.

## Configuration

| Option              | What it is                                                             |
| ------------------- | ---------------------------------------------------------------------- |
| `api_token`         | Vestaboard Cloud API token, from the Developer section of the web app. |
| `checkiday_api_key` | Checkiday API key, for the holidays. Optional; leave it empty to skip. |
| `log_level`         | `debug` while you are working on rules, `info` otherwise.              |
| `dry_run`           | Log what would be sent instead of sending it. Good for testing.        |

Home Assistant access needs no configuration: the app talks to it through the
Supervisor proxy using the token Supervisor provides.

The app used to talk to the older Read/Write API and called this option
`read_write_key`. If you are updating from that version, the old value is gone:
create a Cloud API token in the web app and paste it into `api_token`.

## The gallery

Press **Open Web UI** above to see every piece of art the app can put on the
board, each drawn chip for chip and labeled with the name to ask for it by.
**Show in sidebar** on this page puts it a click away.

The cards are grouped by category, which is what a rotation picks within: `art`
for the daytime pieces, `bedtime` for the quiet ones. The heading over a group
is the word to send as `category`.

**Capture the board** saves whatever the board is showing right now as a new
piece, which joins that category's rotation immediately. The **Into** menu
beside the button is which category it lands in. Captures are files under
`/data/art` in the app's own storage, so they survive restarts and updates; the
gallery marks them `saved`. Capturing the same board into the same category
twice keeps one copy.

Each saved piece has a **Delete** button, which asks first and then throws the
file away. Pieces that come from `art.py` have no button: they are code.

## Actions

The app listens for events, so an automation can put something on the board.
Use the **Fire event** action (under *Other actions* in the automation editor):

| Event                 | What it does                                                 |
| --------------------- | ------------------------------------------------------------ |
| `vestaboard_show_art` | Shows pixel art. Optional `category` or `name` picks it.     |
| `vestaboard_text`     | Shows the `text` it is given, laid out by the board.         |
| `vestaboard_eggs`     | Shows the egg numbers: `today`, `mtd` and `ytd`.             |
| `vestaboard_smoker`   | Shows a cook: `food`, `air`, and a `duration` to count down. |
| `vestaboard_forecast` | Shows the date, the day's weather, and its high and low.     |
| `vestaboard_fetch_holidays` | Looks up today's holidays and writes them down.        |

A half-hourly rotation, then, is an automation and not a code change:

```yaml
alias: Vestaboard art
triggers:
  - trigger: time_pattern
    minutes: "/30"
actions:
  - event: vestaboard_show_art
```

Leave out `event_data` and the app picks at random from the `art` category,
never repeating the piece already on the board. To pick within another
category -- the board winding down for the night, on its own automation:

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

To ask for one piece by name, whichever category it is in:

```yaml
actions:
  - event: vestaboard_show_art
    event_data:
      name: rainbow
```

The names are the keys of `ARTWORKS` in `vestaboard_ha/art.py` -- `rainbow` and
`zzz` are the ones shipped -- plus anything captured or saved into `/data/art`.
The gallery lists the lot with the art next to each name, under the category it
is in. An unknown name, or a category with nothing in it, is logged as an error
and leaves the board alone.

## The forecast

`vestaboard_forecast` puts the day up: the date down the left, the weather
drawn in the middle, and the day's high over its low on the right, each in
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

The three keys are a daily forecast entry as Home Assistant hands it over.

Temperatures are read as **Celsius**, which is what a forecast gives unless
your Home Assistant is set to US customary units. If it is, add a `unit` and
both columns still come out right -- the entity knows which it means:

```yaml
    event_data:
      unit: "{{ state_attr('weather.home', 'temperature_unit') }}"
      condition: "{{ forecasts['weather.home'].forecast[0].condition }}"
      high: "{{ forecasts['weather.home'].forecast[0].temperature }}"
      low: "{{ forecasts['weather.home'].forecast[0].templow }}"
```

A plain `C` or `F` works too. Anything missing shows as `?` rather than
costing the rest of the board.

`condition` is any of the fifteen a weather entity reports -- `sunny`,
`partlycloudy`, `cloudy`, `rainy`, `pouring`, `lightning`, `lightning-rainy`,
`snowy`, `snowy-rainy`, `hail`, `fog`, `windy`, `windy-variant`, `clear-night`
and `exceptional` -- and each is drawn in the four chips in the middle. One we
do not know draws a `?`.

The date is today in Home Assistant's timezone. Send a `date` (an ISO date, or
a forecast's own `datetime`) to put a different day up.

## A message

`vestaboard_text` puts whatever you give it on the board, and the board is what
lays it out -- centered, wrapped over as many of the three rows as it needs.

```yaml
alias: Say the temperature
triggers:
  - trigger: time
    at: "07:00:00"
actions:
  - event: vestaboard_text
    event_data:
      text: "{{ states('sensor.outside_temperature') | round }} DEGREES"
```

A template is the point of it: the automation works out what to say without a
push to `rules.py`. An event with no `text`, or with nothing but spaces, is
logged and leaves the board showing what it has -- the Cloud API does not take
a blank message. Anything else goes to the board as written, so a message the
board will not take is an error in the log and nothing on the board.

## The egg numbers

`vestaboard_eggs` puts a hen on the left of the board and three numbers down
the right: `today`, a count of eggs, and `mtd` and `ytd`, eggs per day so far
this month and this year. Which hen is a toss-up each time, from the few drawn
into `rules.py`.

```yaml
alias: Eggs to the board
triggers:
  - trigger: state
    entity_id: counter.eggs
actions:
  - event: vestaboard_eggs
    event_data:
      today: "{{ states('counter.eggs') | int }}"
      mtd: "{{ states('sensor.eggs_per_day_this_month') | float }}"
      ytd: "{{ states('sensor.eggs_per_day_this_year') | float }}"
```

The automation is what knows the numbers; the app only lays them out. Each is
written against the board's right edge, keeping as many decimals as fit in what
its label has left it, so a daily average reads `2.75` under ten and `12.3`
over it, and drops the decimal point entirely past a hundred. A number too big
for its chips shows as `999+`, and one that is missing or is not a number shows
as `?` -- the other two still go up.

## A cook

`vestaboard_smoker` puts smoke on the left of the board and a cook's numbers
down the right: `food`, the probe in the meat, and `air`, the smoker itself.
Send a `duration` as well and a third row counts it down; leave it out and the
board is the two temperatures.

```yaml
alias: Smoker to the board
triggers:
  - trigger: time_pattern
    minutes: "/5"
actions:
  - event: vestaboard_smoker
    event_data:
      food: "{{ states('sensor.meat_probe') | float }}"
      air: "{{ states('sensor.smoker_temperature') | float }}"
      duration: >-
        {{ state_attr('timer.smoker', 'remaining')
           if is_state('timer.smoker', 'active') }}
```

The duration is seconds as a number -- which is what subtracting one timestamp
from another gives -- or `H:MM:SS` or `H:MM` as a string, the form a timer
entity's `remaining` attribute comes in. Seconds are dropped rather than
rounded, so `2:06` means two hours and six minutes still to go, and a cook that
has run over sits at `0:00`.

A duration that is missing, or that a template rendered to nothing, counts as no
duration at all -- which is what the `if` in that last template is for: the
TIMER row is on the board while the timer is running and gone when it is not. Temperatures go up as whole degrees with an `F`
after them -- the board has a degree sign on the flagship, but this one is a
Note, which draws that flap as a red heart -- and a reading that is missing or
is not a number shows as `?` while the other rows still go up. A cook past ten
hours needs a chip more for its timer, and every row steps left together to
give it one, so the readings stay in a column.

## The holidays

`vestaboard_fetch_holidays` is the one action that puts nothing on the board.
It asks Checkiday which of its several thousand holidays fall today -- the
national days, the awareness months, and the properly obscure ones -- and keeps
the answer, so that something later can make a board out of it.

```yaml
alias: Vestaboard holidays
triggers:
  - trigger: time
    at: "06:30:00"
actions:
  - event: vestaboard_fetch_holidays
```

It needs a `checkiday_api_key` on the **Configuration** tab above. Without one
it says so in the log and leaves everything alone, so an install that does not
want holidays can leave the option empty. A free key is a hundred requests a
month, which is why the day is only ever looked up once.

What it keeps is two sets of files under `/data/holidays`, which is the app's
own storage and survives restarts and updates: one file per day, holding the
ids of that day's holidays, and one file per holiday, saying what an id means.
A day is only ever fetched once, so firing the event twice in a day costs
nothing of the monthly allowance the key comes with, and a holiday's name is
only ever fetched once however many years it comes round.

To ask about a day that is already written down -- a holiday added to Checkiday
partway through it, most likely:

```yaml
actions:
  - event: vestaboard_fetch_holidays
    event_data:
      refresh: true
```

A look-up that goes wrong spends a request the same as one that works, so a day
that has failed three times is left until tomorrow instead of being retried all
afternoon. `refresh: true` is also how you try again once whatever was wrong is
fixed.

There is no way to ask about another day. Choosing the date needs a Pro plan
and choosing the timezone it is reckoned in needs an Enterprise one, so the app
asks what today is and files the answer under whichever day Checkiday says that
was. On a free key that is worked out in US Central time, so fire the
automation in the morning, when that is the same day it is here.

## Changing what gets sent

Rules live in `vestaboard_ha/rules.py` in the repository. Edit that file, push
to `main`, then come back to this page and press **Update**.
