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
    assert settings.supervisor_token == "supervisor-token"
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
    assert settings.supervisor_token == ""


def test_a_broker_is_named_in_the_environment_outside_supervisor(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "OPTIONS_PATH", tmp_path / "missing.json")
    monkeypatch.setenv("MQTT_HOST", "mosquitto.local")
    monkeypatch.setenv("MQTT_PORT", "8883")
    monkeypatch.setenv("MQTT_USERNAME", "board")
    monkeypatch.setenv("MQTT_PASSWORD", "hunter2")
    monkeypatch.setenv("MQTT_SSL", "yes")

    broker = settings_module.load().mqtt

    assert broker == settings_module.Broker(
        host="mosquitto.local", port=8883, username="board", password="hunter2", ssl=True
    )


def test_a_broker_needs_only_a_host(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "OPTIONS_PATH", tmp_path / "missing.json")
    monkeypatch.setenv("MQTT_HOST", "mosquitto.local")
    for name in ("MQTT_PORT", "MQTT_USERNAME", "MQTT_PASSWORD", "MQTT_SSL"):
        monkeypatch.delenv(name, raising=False)

    broker = settings_module.load().mqtt

    assert broker == settings_module.Broker(host="mosquitto.local")
    assert broker.port == 1883


def test_no_host_means_no_broker_named(tmp_path, monkeypatch):
    # Under Supervisor the broker is asked for at startup instead, and outside
    # it the device simply is not put on one.
    monkeypatch.setattr(settings_module, "OPTIONS_PATH", tmp_path / "missing.json")
    monkeypatch.delenv("MQTT_HOST", raising=False)

    assert settings_module.load().mqtt is None

    monkeypatch.setenv("MQTT_HOST", "   ")
    assert settings_module.load().mqtt is None


def test_the_device_state_lives_in_the_app_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "OPTIONS_PATH", tmp_path / "missing.json")
    monkeypatch.delenv("STATE_PATH", raising=False)

    assert settings_module.load().state_path == settings_module.DATA_DIR / "device.json"

    monkeypatch.setenv("STATE_PATH", "/somewhere/else/device.json")
    assert settings_module.load().state_path == Path("/somewhere/else/device.json")


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


def test_the_manifest_asks_supervisor_for_the_mqtt_service():
    # Supervisor only hands out the broker's login to an app that has said it
    # uses the service -- and "want" rather than "need", so that the app still
    # starts, events and all, on a system with no broker.
    manifest = CONFIG.read_text()

    assert re.search(r"^\s+-\s*mqtt:want\s*$", manifest, re.M)
