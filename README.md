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
5. On its **Configuration** tab, paste the Vestaboard Read/Write key.
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
    app.py                 wires rules to the scheduler and the event stream
    registry.py            the @on_schedule and @on_state decorators
    board.py               Vestaboard Read/Write API client
    hass.py                Home Assistant websocket + REST client
    charcodes.py           character codes, for exact placement
    settings.py            app options, or env vars outside Home Assistant
  tests/
docker-compose.yml         fallback for installs without the app store
```

## Writing rules

```python
@on_schedule(hour=7, minute=0)
async def good_morning(ctx):
    await ctx.board.send_text("GOOD MORNING")


@on_state("binary_sensor.front_door", to="on")
async def front_door_opened(ctx, event):
    await ctx.board.send_text("WELCOME HOME")
```

`ctx.board` sends to the board, `ctx.hass` reads state and calls services.
Schedules use APScheduler's cron fields in the container's timezone, which
Home Assistant sets to match the one configured for the house.

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
