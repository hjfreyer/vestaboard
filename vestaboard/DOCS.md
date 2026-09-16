# Vestaboard

Pushes messages to my Vestaboard in response to Home Assistant events.

## Configuration

| Option      | What it is                                                             |
| ----------- | ---------------------------------------------------------------------- |
| `api_token` | Vestaboard Cloud API token, from the Developer section of the web app. |
| `log_level` | `debug` while you are working on rules, `info` otherwise.              |
| `dry_run`   | Log what would be sent instead of sending it. Good for testing.        |

Home Assistant access needs no configuration: the app talks to it through the
Supervisor proxy using the token Supervisor provides.

The app used to talk to the older Read/Write API and called this option
`read_write_key`. If you are updating from that version, the old value is gone:
create a Cloud API token in the web app and paste it into `api_token`.

## The gallery

Press **Open Web UI** above to see every piece of art the app can put on the
board, each drawn chip for chip and labeled with the name to ask for it by.
**Show in sidebar** on this page puts it a click away.

**Capture the board** saves whatever the board is showing right now as a new
piece, which joins the rotation immediately. Captures are files under
`/data/art` in the app's own storage, so they survive restarts and updates; the
gallery marks them `saved`. Capturing the same board twice keeps one copy.

Each saved piece has a **Delete** button, which asks first and then throws the
file away. Pieces that come from `art.py` have no button: they are code.

## Actions

The app listens for events, so an automation can put something on the board.
Use the **Fire event** action (under *Other actions* in the automation editor):

| Event                  | What it does                                          |
| ---------------------- | ----------------------------------------------------- |
| `vestaboard_show_art`  | Shows a piece of pixel art. Optional `name` picks one. |
| `vestaboard_text`      | Shows the `text` it is given, laid out by the board.   |
| `vestaboard_eggs`      | Shows the egg numbers: `today`, `mtd` and `ytd`.      |

A half-hourly rotation, then, is an automation and not a code change:

```yaml
alias: Vestaboard art
triggers:
  - trigger: time_pattern
    minutes: "/30"
actions:
  - event: vestaboard_show_art
```

Leave out `event_data` and the app picks at random, never repeating the piece
already on the board. To ask for one by name:

```yaml
actions:
  - event: vestaboard_show_art
    event_data:
      name: rainbow
```

The names are the keys of `ARTWORKS` in `vestaboard_ha/art.py` -- `rainbow` is
the only one shipped -- plus anything captured or saved into `/data/art`. The
gallery lists the lot with the art next to each name. An unknown name is logged
as an error and leaves the board alone.

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

## Changing what gets sent

Rules live in `vestaboard_ha/rules.py` in the repository. Edit that file, push
to `main`, then come back to this page and press **Update**.
