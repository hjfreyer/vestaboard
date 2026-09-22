"""Configuration, loaded from app options or environment variables.

Two supported runtimes:

* As a Home Assistant app (formerly add-on). Supervisor writes the options to
  ``/data/options.json`` and injects ``SUPERVISOR_TOKEN``; Home Assistant is
  reachable through the Supervisor proxy, so there is nothing to configure.
* Anywhere else (laptop, plain Docker). Everything comes from environment
  variables and you supply a long-lived access token yourself.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

#: Supervisor keeps /data across restarts and updates, and it is the only
#: directory that survives either, so saved art goes in it.
DATA_DIR = Path("/data")
OPTIONS_PATH = DATA_DIR / "options.json"
DEFAULT_ART_DIR = DATA_DIR / "art"
DEFAULT_HOLIDAYS_DIR = DATA_DIR / "holidays"

# Supervisor proxies the Home Assistant API for apps that ask for it.
SUPERVISOR_REST = "http://supervisor/core/api"
SUPERVISOR_WS = "ws://supervisor/core/websocket"

# Where the art gallery listens. Not an option: Supervisor only proxies the
# port named as ``ingress_port`` in config.yaml, so the two have to agree.
DEFAULT_WEB_PORT = 8099


@dataclass(frozen=True)
class Settings:
    api_token: str
    rest_url: str
    ws_url: str
    hass_token: str
    checkiday_api_key: str = ""
    log_level: str = "info"
    dry_run: bool = False
    web_port: int = DEFAULT_WEB_PORT
    art_dir: Path = DEFAULT_ART_DIR
    holidays_dir: Path = DEFAULT_HOLIDAYS_DIR

    @property
    def has_hass(self) -> bool:
        return bool(self.hass_token)

    @property
    def has_checkiday(self) -> bool:
        return bool(self.checkiday_api_key)


def _load_options() -> dict:
    if not OPTIONS_PATH.exists():
        return {}
    with OPTIONS_PATH.open() as fh:
        return json.load(fh)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw.isdigit() else default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load() -> Settings:
    options = _load_options()

    supervisor_token = os.environ.get("SUPERVISOR_TOKEN", "")
    if supervisor_token:
        rest_url, ws_url = SUPERVISOR_REST, SUPERVISOR_WS
        hass_token = supervisor_token
    else:
        # Local development: point at Home Assistant directly.
        base = os.environ.get("HASS_URL", "http://homeassistant.local:8123").rstrip("/")
        rest_url = f"{base}/api"
        ws_url = base.replace("https://", "wss://").replace("http://", "ws://")
        ws_url = f"{ws_url}/api/websocket"
        hass_token = os.environ.get("HASS_TOKEN", "")

    return Settings(
        api_token=os.environ.get("VESTABOARD_API_TOKEN", options.get("api_token", "")),
        checkiday_api_key=os.environ.get(
            "CHECKIDAY_API_KEY", options.get("checkiday_api_key", "")
        ),
        rest_url=rest_url,
        ws_url=ws_url,
        hass_token=hass_token,
        log_level=os.environ.get("LOG_LEVEL", options.get("log_level", "info")),
        dry_run=_env_bool("DRY_RUN", bool(options.get("dry_run", False))),
        web_port=_env_int("WEB_PORT", DEFAULT_WEB_PORT),
        art_dir=Path(os.environ.get("ART_DIR") or DEFAULT_ART_DIR),
        holidays_dir=Path(os.environ.get("HOLIDAYS_DIR") or DEFAULT_HOLIDAYS_DIR),
    )
