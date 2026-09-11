# vestaboard

Pushes messages to my Vestaboard, on a schedule and in response to Home
Assistant events. Built for my house specifically; you are welcome to steal
from it.

This repository is a **Home Assistant add-on repository**. Home Assistant
installs the add-on from GitHub and offers an Update button when I push.

## Installing

1. In Home Assistant, go to **Settings → Add-ons → Add-on Store**.
2. Three-dot menu (top right) → **Repositories**.
3. Add `https://github.com/hjfreyer/vestaboard` and close the dialog.
4. The **Vestaboard** add-on appears at the bottom of the store. Install it.
5. On the add-on's **Configuration** tab, paste the Vestaboard Read/Write key.
6. Start it, and watch the **Log** tab.

Set `dry_run: true` in the configuration first if you want to see what it would
send before letting it touch the board.

## Updating

1. Edit `vestaboard/vestaboard_ha/rules.py` and push to `main`.
2. CI bumps the add-on's version number, which is what makes Home Assistant
   notice there is something new.
3. In Home Assistant, open the add-on and press **Update**. (Supervisor checks
   the repository every so often; the store's three-dot **Check for updates**
   forces it.)

Nothing to SSH into, and a broken push does not reach the board until the
Update button is pressed.

## Layout

```
repository.yaml            marks this repo as an add-on repository
vestaboard/                the add-on; also the Docker build context
  config.yaml              add-on manifest, including the version number
  Dockerfile, build.yaml   how Supervisor builds it
  vestaboard_ha/
    rules.py               >>> the file worth editing <<<
    app.py                 wires rules to the scheduler and the event stream
    registry.py            the @on_schedule and @on_state decorators
    board.py               Vestaboard Read/Write API client
    hass.py                Home Assistant websocket + REST client
    charcodes.py           character codes, for exact placement
    settings.py            add-on options, or env vars outside Home Assistant
  tests/
docker-compose.yml         fallback for installs without the add-on store
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
page. Inside the add-on none of this is needed.
