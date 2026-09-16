# Vestaboard

Puts the Vestaboard in Home Assistant as a device: a channel to tune it to, a
message to give it, and the events it always answered to.

## Configuration

| Option      | What it is                                                             |
| ----------- | ---------------------------------------------------------------------- |
| `api_token` | Vestaboard Cloud API token, from the Developer section of the web app. |
| `log_level` | `debug` while you are working on rules, `info` otherwise.              |
| `dry_run`   | Log what would be sent instead of sending it. Good for testing.        |

Home Assistant access needs no configuration: the app talks to it through the
Supervisor proxy using the token Supervisor provides. Nor does the broker: with
the **Mosquitto broker** app installed and the **MQTT** integration set up,
Supervisor tells the app where it is, and the device appears under MQTT the
next time the app starts. Without a broker the app runs on events alone, and
says so in the log.

The app used to talk to the older Read/Write API and called this option
`read_write_key`. If you are updating from that version, the old value is gone:
create a Cloud API token in the web app and paste it into `api_token`.

## The device

Under **Settings → Devices & services → MQTT** there is a device called
**Vestaboard**, with these on it:

| Entity                | What it is                                                        |
| --------------------- | ----------------------------------------------------------------- |
| **Channel**           | What the board shows: **Hold**, **Art**, **Message** or **Eggs**. |
| **Piece**             | Which piece the Art channel shows: a name, or **Random**.         |
| **Art rotation**      | Minutes between random pieces. 0 keeps the one that is up.        |
| **Message**           | What the Message channel says. Empty clears the board.            |
| **Next piece**        | Another random piece, on the Art channel.                         |
| **Capture the board** | Saves what is on the board to the gallery, as the button below.   |
| **Showing**           | What is on the board, in a few words.                             |

The board shows the channel, and only the channel: change it and the board
redraws, change the piece or the message and the channel showing it redraws,
and otherwise nothing touches it. **Hold** draws nothing, for a board somebody
has written on by hand, and is where a fresh install starts.

A schedule is an automation on the select, like any other select:

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

A message is the text entity and then the channel, or the `vestaboard_text`
event below, which is both at once.

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

The app also listens for events, which are the device's remote control: each
sets a control and tunes to a channel, so the board shows what was asked for
and the Channel select agrees. Use the **Fire event** action (under *Other
actions* in the automation editor):

| Event                  | What it does                                                    |
| ---------------------- | --------------------------------------------------------------- |
| `vestaboard_show_art`  | Tunes to Art. Optional `name` holds that piece; none is Random.  |
| `vestaboard_text`      | Makes the `text` it is given the Message and tunes to it.       |
| `vestaboard_eggs`      | Keeps the egg numbers `today`, `mtd` and `ytd` and tunes to Eggs. |

The art rotation is the device's own **Art rotation**, so a half-hourly
automation firing `vestaboard_show_art` is no longer wanted: it would tune to
Art every half hour. Leave out `event_data` and the piece goes back to Random,
never repeating the one already on the board. To ask for one by name:

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

`vestaboard_text` makes whatever you give it the device's Message and tunes to
it, and the board is what lays it out -- centered, wrapped over as many of the
three rows as it needs.

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
board will not take is an error in the log and nothing on the board. Setting
the **Message** text on the device to nothing is different: that clears the
board.

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
as `?` -- the other two still go up. The numbers are kept, so tuning to Eggs
from the device page later shows the last ones sent.

## Changing what gets sent

Rules live in `vestaboard_ha/rules.py` in the repository. Edit that file, push
to `main`, then come back to this page and press **Update**.
