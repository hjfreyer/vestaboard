import json

from vestaboard_ha import settings as settings_module


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


def test_no_token_means_no_home_assistant(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "OPTIONS_PATH", tmp_path / "missing.json")
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    monkeypatch.delenv("HASS_TOKEN", raising=False)
    monkeypatch.delenv("VESTABOARD_API_TOKEN", raising=False)

    assert not settings_module.load().has_hass
