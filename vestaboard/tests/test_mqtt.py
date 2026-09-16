import asyncio

import aiomqtt
import pytest

from vestaboard_ha import mqtt
from vestaboard_ha.device import AVAILABILITY_TOPIC, STATUS_TOPIC
from vestaboard_ha.settings import Broker

BROKER = Broker(host="mosquitto", port=1883, username="u", password="p")


class FakeMessage:
    def __init__(self, topic, payload):
        self.topic = aiomqtt.Topic(topic)
        self.payload = payload


class FakeLink:
    """What aiomqtt's client looks like from here: a context, a queue, two calls."""

    def __init__(self, messages=(), then=None):
        self.messages_to_serve = list(messages)
        self.then = then
        self.subscribed = []
        self.published = []
        self.entered = 0

    async def __aenter__(self):
        self.entered += 1
        if isinstance(self.then, aiomqtt.MqttError) and not self.messages_to_serve:
            raise self.then
        return self

    async def __aexit__(self, *exc):
        return False

    async def subscribe(self, topic):
        self.subscribed.append(topic)

    async def publish(self, topic, payload, retain=False):
        self.published.append((topic, payload, retain))

    @property
    def messages(self):
        return self._serve()

    async def _serve(self):
        for message in self.messages_to_serve:
            yield message
        if self.then is not None:
            raise self.then


class FakeDevice:
    def __init__(self):
        self.received_messages = []
        self.connections = 0
        self.disconnections = 0
        self.publish = None

    async def connected(self, publish):
        self.connections += 1
        self.publish = publish

    async def disconnected(self):
        self.disconnections += 1

    async def received(self, topic, payload):
        self.received_messages.append((topic, payload))


@pytest.mark.asyncio
async def test_one_connection_subscribes_hands_over_and_feeds(monkeypatch):
    link = FakeLink(
        [
            FakeMessage("vestaboard/channel/set", b"Art"),
            FakeMessage(STATUS_TOPIC, b"online"),
            FakeMessage("vestaboard/message/set", "already text"),
        ]
    )
    monkeypatch.setattr(mqtt, "client", lambda broker: link)
    device = FakeDevice()

    await mqtt.serve_once(BROKER, device)

    assert link.subscribed == ["vestaboard/+/set", STATUS_TOPIC]
    assert device.connections == 1
    assert device.received_messages == [
        ("vestaboard/channel/set", "Art"),
        (STATUS_TOPIC, "online"),
        ("vestaboard/message/set", "already text"),
    ]


@pytest.mark.asyncio
async def test_the_device_publishes_through_the_link(monkeypatch):
    link = FakeLink()
    monkeypatch.setattr(mqtt, "client", lambda broker: link)
    device = FakeDevice()

    await mqtt.serve_once(BROKER, device)
    await device.publish("vestaboard/channel", "Art", retain=True)
    await device.publish("vestaboard/next", "PRESS")

    assert link.published == [
        # The goodbye, from the stream having ended; then the device's own.
        (AVAILABILITY_TOPIC, "offline", True),
        ("vestaboard/channel", "Art", True),
        ("vestaboard/next", "PRESS", False),
    ]


@pytest.mark.asyncio
async def test_leaving_on_purpose_says_offline(monkeypatch):
    # A clean disconnect makes the broker drop the will, so the device has to
    # say goodbye itself.
    link = FakeLink(then=asyncio.CancelledError())
    monkeypatch.setattr(mqtt, "client", lambda broker: link)

    with pytest.raises(asyncio.CancelledError):
        await mqtt.serve_once(BROKER, FakeDevice())

    assert link.published[-1] == (AVAILABILITY_TOPIC, "offline", True)


@pytest.mark.asyncio
async def test_a_broken_link_is_not_asked_to_say_goodbye(monkeypatch):
    class Broken(FakeLink):
        async def publish(self, topic, payload, retain=False):
            raise aiomqtt.MqttError("gone")

    link = Broken(then=aiomqtt.MqttError("gone"))
    monkeypatch.setattr(mqtt, "client", lambda broker: link)

    with pytest.raises(aiomqtt.MqttError, match="gone"):
        await mqtt.serve_once(BROKER, FakeDevice())


@pytest.mark.asyncio
async def test_bytes_that_are_not_text_still_arrive(monkeypatch):
    link = FakeLink([FakeMessage("vestaboard/message/set", b"\xff\xfe")])
    monkeypatch.setattr(mqtt, "client", lambda broker: link)
    device = FakeDevice()

    await mqtt.serve_once(BROKER, device)

    [(_, payload)] = device.received_messages
    assert payload == "��"


@pytest.mark.asyncio
async def test_the_link_is_kept_up_through_failures(monkeypatch, caplog):
    attempts = [
        FakeLink(then=aiomqtt.MqttError("connection refused")),
        FakeLink(
            [FakeMessage("vestaboard/channel/set", b"Art")],
            then=aiomqtt.MqttError("gone"),
        ),
        FakeLink(then=RuntimeError("something else entirely")),
        FakeLink(then=asyncio.CancelledError()),
    ]
    monkeypatch.setattr(mqtt, "client", lambda broker: attempts.pop(0))
    monkeypatch.setattr(mqtt, "INITIAL_BACKOFF_SECONDS", 0)
    device = FakeDevice()

    with pytest.raises(asyncio.CancelledError):
        await mqtt.run(BROKER, device)

    assert attempts == []
    assert device.connections == 3
    # Told each time the link went, so it stops trying to publish into it.
    assert device.disconnections == 3
    assert device.received_messages == [("vestaboard/channel/set", "Art")]
    assert "connection refused" in caplog.text
    assert "something else entirely" in caplog.text


@pytest.mark.asyncio
async def test_a_stream_that_simply_ends_is_reconnected(monkeypatch, caplog):
    attempts = [FakeLink(), FakeLink(then=asyncio.CancelledError())]
    monkeypatch.setattr(mqtt, "client", lambda broker: attempts.pop(0))
    monkeypatch.setattr(mqtt, "INITIAL_BACKOFF_SECONDS", 0)
    device = FakeDevice()

    with pytest.raises(asyncio.CancelledError):
        await mqtt.run(BROKER, device)

    assert device.connections == 2
    assert "connection closed" in caplog.text


@pytest.mark.asyncio
async def test_the_client_carries_the_login_and_the_last_will():
    link = mqtt.client(BROKER)

    assert link.identifier == mqtt.CLIENT_ID
    assert link._client._username == b"u"
    assert link._client._password == b"p"
    # Should we go without a word, the broker says so for us.
    assert link._client._will_topic == AVAILABILITY_TOPIC.encode()
    assert link._client._will_payload == b"offline"
    assert link._client._will_retain
