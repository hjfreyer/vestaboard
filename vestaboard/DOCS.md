# Vestaboard

Pushes messages to my Vestaboard on a schedule and in response to Home
Assistant events.

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

## Actions

The app listens for events, so an automation can put something on the board.
Use the **Fire event** action (under *Other actions* in the automation editor):

| Event                  | What it does                                          |
| ---------------------- | ----------------------------------------------------- |
| `vestaboard_show_art`  | Shows a piece of pixel art. Optional `name` picks one. |

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
      name: heart
```

The names are the keys of `ARTWORKS` in `vestaboard_ha/art.py`: `sunset`,
`heart`, `rainbow`, `invader`, `mountain`, `flower`, `party`, and the gallery
lists them with the art next to each one. An unknown name is logged as an error
and leaves the board alone.

## Changing what gets sent

Rules live in `vestaboard_ha/rules.py` in the repository. Edit that file, push
to `main`, then come back to this page and press **Update**.
