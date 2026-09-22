import json
import re
from pathlib import Path

from vestaboard_ha import settings as settings_module

CONFIG = Path(__file__).resolve().parents[1] / "config.yaml"


def test_addon_mode_uses_the_supervisor_proxy(tmp_path, monkeypatch):
    options = tmp_path / "options.json"
    options.write_text(json.dumps({"api_token": "from-options", "log_level": "debug"}))
    monkeypatch.setattr(settings_module, "OPTIONS_PATH", options)
    monkeypatch.setenv("SUPERVISOR_TOKEN", "supervisor-token")
    monkeypatch.delenv("VESTABOARD_API_TOKEN", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    settings = settings_module.load()

    assert settings.api_token == "from-options"
    assert settings.log_level == "debug"
    assert settings.hass_token == "supervisor-token"
    assert settings.rest_url == settings_module.SUPERVISOR_REST
    assert settings.ws_url == settings_module.SUPERVISOR_WS
    assert settings.has_hass


def test_local_mode_builds_urls_from_hass_url(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "OPTIONS_PATH", tmp_path / "missing.json")
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    monkeypatch.setenv("HASS_URL", "https://ha.example.com:8123/")
    monkeypatch.setenv("HASS_TOKEN", "long-lived")
    monkeypatch.setenv("VESTABOARD_API_TOKEN", "from-env")

    settings = settings_module.load()

    assert settings.rest_url == "https://ha.example.com:8123/api"
    assert settings.ws_url == "wss://ha.example.com:8123/api/websocket"
    assert settings.api_token == "from-env"


def test_the_gallery_port_matches_ingress_unless_told_otherwise(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "OPTIONS_PATH", tmp_path / "missing.json")
    monkeypatch.delenv("WEB_PORT", raising=False)

    assert settings_module.load().web_port == settings_module.DEFAULT_WEB_PORT

    monkeypatch.setenv("WEB_PORT", "9000")
    assert settings_module.load().web_port == 9000

    monkeypatch.setenv("WEB_PORT", "not a port")
    assert settings_module.load().web_port == settings_module.DEFAULT_WEB_PORT


def test_saved_art_lives_in_the_app_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "OPTIONS_PATH", tmp_path / "missing.json")
    monkeypatch.delenv("ART_DIR", raising=False)

    assert settings_module.load().art_dir == settings_module.DATA_DIR / "art"

    monkeypatch.setenv("ART_DIR", "/somewhere/else")
    assert settings_module.load().art_dir == Path("/somewhere/else")


def test_no_token_means_no_home_assistant(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "OPTIONS_PATH", tmp_path / "missing.json")
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    monkeypatch.delenv("HASS_TOKEN", raising=False)
    monkeypatch.delenv("VESTABOARD_API_TOKEN", raising=False)

    assert not settings_module.load().has_hass


def test_the_manifest_proxies_the_port_the_gallery_listens_on():
    # Supervisor proxies ingress_port and nothing else, so a change to one of
    # these without the other leaves the gallery unreachable.
    manifest = CONFIG.read_text()
    port = re.search(r"^ingress_port:\s*(\d+)", manifest, re.M)

    assert re.search(r"^ingress:\s*true", manifest, re.M)
    assert port and int(port.group(1)) == settings_module.DEFAULT_WEB_PORT


def test_the_checkiday_key_comes_from_the_options_or_the_environment(
    tmp_path, monkeypatch
):
    options = tmp_path / "options.json"
    options.write_text(json.dumps({"checkiday_api_key": "from-options"}))
    monkeypatch.setattr(settings_module, "OPTIONS_PATH", options)
    monkeypatch.delenv("CHECKIDAY_API_KEY", raising=False)

    settings = settings_module.load()
    assert settings.checkiday_api_key == "from-options"
    assert settings.has_checkiday

    monkeypatch.setenv("CHECKIDAY_API_KEY", "from-env")
    assert settings_module.load().checkiday_api_key == "from-env"


def test_no_checkiday_key_is_a_holiday_fetch_that_will_not_run(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "OPTIONS_PATH", tmp_path / "missing.json")
    monkeypatch.delenv("CHECKIDAY_API_KEY", raising=False)

    assert not settings_module.load().has_checkiday


def test_the_holidays_live_in_the_app_storage_beside_the_art(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "OPTIONS_PATH", tmp_path / "missing.json")
    monkeypatch.delenv("HOLIDAYS_DIR", raising=False)

    assert settings_module.load().holidays_dir == settings_module.DATA_DIR / "holidays"

    monkeypatch.setenv("HOLIDAYS_DIR", "/somewhere/else")
    assert settings_module.load().holidays_dir == Path("/somewhere/else")
