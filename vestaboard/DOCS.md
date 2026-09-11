# Vestaboard

Pushes messages to my Vestaboard on a schedule and in response to Home
Assistant events.

## Configuration

| Option           | What it is                                                        |
| ---------------- | ----------------------------------------------------------------- |
| `read_write_key` | Vestaboard Read/Write API key, from the Vestaboard developer site. |
| `log_level`      | `debug` while you are working on rules, `info` otherwise.          |
| `dry_run`        | Log what would be sent instead of sending it. Good for testing.    |

Home Assistant access needs no configuration: the app talks to it through the
Supervisor proxy using the token Supervisor provides.

## Changing what gets sent

Rules live in `vestaboard_ha/rules.py` in the repository. Edit that file, push
to `main`, then come back to this page and press **Update**.
