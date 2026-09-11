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

## Changing what gets sent

Rules live in `vestaboard_ha/rules.py` in the repository. Edit that file, push
to `main`, then come back to this page and press **Update**.
