import logging

import aiohttp
import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer

from vestaboard_ha import supervisor
from vestaboard_ha.device import Identity
from vestaboard_ha.settings import Broker

TOKEN = "supervisor-token"


class FakeSupervisor:
    """Answers the two endpoints the app asks, and remembers being asked."""

    def __init__(self, mqtt=None, info=None, status=200, message="no, sorry"):
        self.mqtt = mqtt
        self.info = info
        self.status = status
        self.message = message
        self.headers = []

    def app(self):
        app = web.Application()
        app.router.add_get("/services/mqtt", self.answer(self.mqtt))
        app.router.add_get("/addons/self/info", self.answer(self.info))
        return app

    def answer(self, data):
        async def handler(request):
            self.headers.append(request.headers.get("Authorization"))
            if self.status >= 400:
                return web.json_response(
                    {"result": "error", "message": self.message}, status=self.status
                )
            return web.json_response({"result": "ok", "data": data})

        return handler


async def ask(fake, what, monkeypatch, session):
    server = TestServer(fake.app())
    await server.start_server()
    try:
        url = str(server.make_url("")).rstrip("/")
        monkeypatch.setattr(supervisor, "SUPERVISOR", url)
        return await what(session, TOKEN)
    finally:
        await server.close()


@pytest_asyncio.fixture
async def session():
    async with aiohttp.ClientSession() as session:
        yield session


#: What Supervisor answers for the mqtt service with Mosquitto running: the
#: broker itself, and nothing about availability -- that is the refusal below.
MOSQUITTO = {
    "host": "core-mosquitto",
    "port": 1883,
    "ssl": False,
    "username": "addons",
    "password": "hunter2",
    "protocol": "3.1.1",
    "app": "core_mosquitto",
}


@pytest.mark.asyncio
async def test_the_broker_mosquitto_provides(monkeypatch, session, caplog):
    caplog.set_level(logging.INFO)
    fake = FakeSupervisor(mqtt=MOSQUITTO)

    broker = await ask(fake, supervisor.mqtt_broker, monkeypatch, session)

    assert broker == Broker(
        host="core-mosquitto", port=1883, username="addons", password="hunter2", ssl=False
    )
    assert fake.headers == [f"Bearer {TOKEN}"]
    assert "MQTT broker at core-mosquitto:1883, provided by core_mosquitto" in caplog.text


@pytest.mark.asyncio
async def test_an_older_supervisor_names_the_provider_the_old_way(monkeypatch, session):
    fake = FakeSupervisor(mqtt={**MOSQUITTO, "app": None, "addon": "core_mosquitto"})

    broker = await ask(fake, supervisor.mqtt_broker, monkeypatch, session)

    assert broker is not None
    assert broker.host == "core-mosquitto"


@pytest.mark.asyncio
async def test_no_mosquitto_is_a_refusal_and_no_broker(monkeypatch, session, caplog):
    caplog.set_level(logging.INFO)
    # With no app providing the service, Supervisor does not answer with an
    # empty broker; it refuses the question.
    fake = FakeSupervisor(status=400, message="Service not enabled")

    assert await ask(fake, supervisor.mqtt_broker, monkeypatch, session) is None
    assert "no MQTT broker: no app provides one" in caplog.text
    assert "WARNING" not in caplog.text


@pytest.mark.asyncio
async def test_an_answer_with_no_host_is_a_warning_and_no_broker(
    monkeypatch, session, caplog
):
    fake = FakeSupervisor(mqtt={"port": 1883, "password": "hunter2"})

    assert await ask(fake, supervisor.mqtt_broker, monkeypatch, session) is None
    assert "has no host in it: {'port': 1883}" in caplog.text
    assert "hunter2" not in caplog.text


@pytest.mark.asyncio
async def test_being_refused_is_a_warning_and_no_broker(monkeypatch, session, caplog):
    fake = FakeSupervisor(status=403)

    assert await ask(fake, supervisor.mqtt_broker, monkeypatch, session) is None
    assert "would not say where the MQTT broker is: HTTP 403: no, sorry" in caplog.text


@pytest.mark.asyncio
async def test_an_answer_that_is_not_json_is_a_warning_and_no_broker(
    monkeypatch, session, caplog
):
    app = web.Application()

    async def html(request):
        return web.Response(text="<html>502 Bad Gateway</html>", status=502)

    app.router.add_get("/services/mqtt", html)
    server = TestServer(app)
    await server.start_server()
    try:
        url = str(server.make_url("")).rstrip("/")
        monkeypatch.setattr(supervisor, "SUPERVISOR", url)
        assert await supervisor.mqtt_broker(session, TOKEN) is None
    finally:
        await server.close()
    assert "HTTP 502: not JSON" in caplog.text


@pytest.mark.asyncio
async def test_no_supervisor_at_all_is_a_warning_and_no_broker(
    monkeypatch, session, caplog
):
    # Nothing listens here.
    monkeypatch.setattr(supervisor, "SUPERVISOR", "http://127.0.0.1:1")

    assert await supervisor.mqtt_broker(session, TOKEN) is None
    assert "could not ask Supervisor for the MQTT broker" in caplog.text


@pytest.mark.asyncio
async def test_the_app_learns_its_version_and_its_page(monkeypatch, session):
    fake = FakeSupervisor(
        info={"slug": "a1b2c3d4_vestaboard", "version": "0.1.14", "ingress": True}
    )

    identity = await ask(fake, supervisor.identity, monkeypatch, session)

    assert identity == Identity(
        version="0.1.14",
        configuration_url="homeassistant://hassio/ingress/a1b2c3d4_vestaboard",
    )


@pytest.mark.asyncio
async def test_without_ingress_there_is_no_page_to_link(monkeypatch, session):
    fake = FakeSupervisor(info={"slug": "local_vestaboard", "version": "0.1.14"})

    identity = await ask(fake, supervisor.identity, monkeypatch, session)

    assert identity == Identity(version="0.1.14", configuration_url=None)


@pytest.mark.asyncio
async def test_an_app_supervisor_will_not_describe_says_nothing(
    monkeypatch, session, caplog
):
    fake = FakeSupervisor(status=500)

    assert await ask(fake, supervisor.identity, monkeypatch, session) == Identity()
    assert "would not say what this app is: HTTP 500: no, sorry" in caplog.text

    monkeypatch.setattr(supervisor, "SUPERVISOR", "http://127.0.0.1:1")
    assert await supervisor.identity(session, TOKEN) == Identity()
