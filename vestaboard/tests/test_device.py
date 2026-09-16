import asyncio
import json

import pytest

from vestaboard_ha import art, charcodes, registry
from vestaboard_ha import device as device_module
from vestaboard_ha.board import BoardError
from vestaboard_ha.device import (
    AVAILABILITY_TOPIC,
    DISCOVERY_TOPIC,
    STATUS_TOPIC,
    Device,
    Identity,
    State,
    command_topic,
    control_of,
    state_topic,
)
from vestaboard_ha.library import Library

#: How long the test channels wait between rotations: long enough to be seen
#: not to have fired, short enough to wait for.
TICK = 0.05


class FakeBoard:
    def __init__(self, grid=None, error=None):
        self.grids = []
        self.sent = []
        self.grid = grid or charcodes.blank_grid()
        self.error = error

    async def send_characters(self, grid):
        self.grids.append(grid)

    async def send_text(self, text):
        self.sent.append(text)

    async def read(self):
        if self.error is not None:
            raise self.error
        return self.grid


class FakeContext:
    def __init__(self, tmp_path, board=None):
        self.board = board or FakeBoard()
        self.art = Library(tmp_path / "art")
        self.device = Device(tmp_path / "device.json")


class Recorder:
    """Stands in for the broker: keeps every message the device publishes."""

    def __init__(self):
        self.messages = []

    async def __call__(self, topic, payload, *, retain=False):
        self.messages.append((topic, payload, retain))

    def on(self, topic):
        return [payload for t, payload, _ in self.messages if t == topic]

    def last(self, topic):
        return self.on(topic)[-1]

    def description(self):
        return json.loads(self.last(DISCOVERY_TOPIC))


@pytest.fixture
def channels(monkeypatch):
    """Channels of our own, so the tests do not lean on what rules.py ships."""
    monkeypatch.setattr(registry, "CHANNELS", [])

    @registry.channel("hold", label="Hold")
    async def hold(ctx):
        return None

    @registry.channel("art", label="Art", uses=("piece", "rotation"))
    async def art_channel(ctx):
        name = ctx.device.piece or "random"
        ctx.board.grids.append(name)
        if ctx.device.piece is None and ctx.device.rotation:
            ctx.device.redraw_in(TICK)
        return name

    @registry.channel("message", label="Message", uses=("message",))
    async def message(ctx):
        await ctx.board.send_text(ctx.device.message)
        return ctx.device.message or None

    @registry.channel("boom", label="Boom")
    async def boom(ctx):
        raise RuntimeError("kaboom")


async def started(tmp_path, board=None):
    ctx = FakeContext(tmp_path, board)
    await ctx.device.start(ctx)
    return ctx


async def settle():
    """Let a redraw that is due fire, and one that is not, not."""
    await asyncio.sleep(TICK * 2.5)


# -- the state ----------------------------------------------------------------


def test_a_device_that_has_never_been_set_holds(tmp_path):
    state = State.load(tmp_path / "missing.json")

    assert state == State(channel="hold", piece=None, message="", rotation=30, data={})


def test_the_state_comes_back_as_saved(tmp_path):
    path = tmp_path / "device.json"
    State(
        channel="art", piece="rainbow", message="HI", rotation=5, data={"eggs": {"a": 1}}
    ).save(path)

    assert State.load(path) == State(
        channel="art", piece="rainbow", message="HI", rotation=5, data={"eggs": {"a": 1}}
    )


def test_saving_makes_the_directory(tmp_path):
    path = tmp_path / "deeper" / "still" / "device.json"

    State().save(path)

    assert json.loads(path.read_text())["channel"] == "hold"


def test_a_file_that_is_not_a_state_is_ignored(tmp_path, caplog):
    path = tmp_path / "device.json"

    path.write_text("{not json")
    assert State.load(path) == State()
    assert "does not parse" in caplog.text

    path.write_text("[1, 2, 3]")
    assert State.load(path) == State()
    assert "not a device state" in caplog.text


def test_odd_fields_cost_only_themselves(tmp_path):
    path = tmp_path / "device.json"
    path.write_text(
        json.dumps(
            {
                "channel": "art",
                "piece": 7,
                "message": ["no"],
                "rotation": -3,
                "data": {"eggs": {"today": 1}, "junk": "not a dict"},
            }
        )
    )

    assert State.load(path) == State(channel="art", data={"eggs": {"today": 1}})


def test_a_directory_that_cannot_be_written_is_a_warning(tmp_path, caplog):
    path = tmp_path / "file" / "device.json"
    (tmp_path / "file").write_text("in the way")

    State().save(path)

    assert "could not save" in caplog.text


# -- tuning and adjusting -------------------------------------------------------


@pytest.mark.asyncio
async def test_starting_draws_the_channel_it_is_on(tmp_path, channels):
    State(channel="message", message="DINNER").save(tmp_path / "device.json")

    ctx = await started(tmp_path)

    assert ctx.board.sent == ["DINNER"]
    assert ctx.device.showing == "Message: DINNER"


@pytest.mark.asyncio
async def test_starting_on_hold_draws_nothing(tmp_path, channels):
    ctx = await started(tmp_path)

    assert ctx.board.grids == [] and ctx.board.sent == []
    assert ctx.device.showing == "Hold"


@pytest.mark.asyncio
async def test_a_channel_that_no_longer_exists_becomes_hold(tmp_path, channels, caplog):
    State(channel="weather").save(tmp_path / "device.json")

    ctx = await started(tmp_path)

    assert ctx.device.channel == "hold"
    assert "no channel named 'weather'" in caplog.text
    assert json.loads((tmp_path / "device.json").read_text())["channel"] == "hold"


@pytest.mark.asyncio
async def test_tuning_sets_the_controls_switches_and_draws(tmp_path, channels):
    ctx = await started(tmp_path)

    await ctx.device.tune("art", piece="rainbow")

    assert ctx.device.channel == "art"
    assert ctx.device.piece == "rainbow"
    assert ctx.board.grids == ["rainbow"]
    assert ctx.device.showing == "Art: rainbow"


@pytest.mark.asyncio
async def test_tuning_is_remembered_across_a_restart(tmp_path, channels):
    ctx = await started(tmp_path)
    await ctx.device.tune("art", piece="rainbow", rotation=0)

    again = await started(tmp_path)

    assert again.device.channel == "art"
    assert again.device.piece == "rainbow"
    assert again.device.rotation == 0
    assert again.board.grids == ["rainbow"]


@pytest.mark.asyncio
async def test_an_unknown_channel_is_an_error_and_changes_nothing(tmp_path, channels):
    ctx = await started(tmp_path)

    with pytest.raises(ValueError, match="no channel named 'weather'"):
        await ctx.device.tune("weather", message="HI")

    assert ctx.device.channel == "hold"
    assert ctx.device.message == ""


@pytest.mark.asyncio
async def test_a_piece_that_is_not_in_the_library_is_an_error(tmp_path, channels):
    ctx = await started(tmp_path)

    with pytest.raises(ValueError, match="no piece named 'nonesuch'; there is rainbow"):
        await ctx.device.tune("art", piece="nonesuch")

    assert ctx.device.channel == "hold"
    assert ctx.board.grids == []


@pytest.mark.asyncio
async def test_controls_take_only_what_they_are(tmp_path, channels):
    ctx = await started(tmp_path)

    with pytest.raises(ValueError, match="rotation cannot be -1"):
        await ctx.device.adjust(rotation=-1)
    with pytest.raises(ValueError, match="no control named 'volume'"):
        await ctx.device.adjust(volume=11)
    with pytest.raises(ValueError, match="data belongs to a channel"):
        await ctx.device.adjust(data={"today": 1})
    with pytest.raises(ValueError, match="a channel's data is a dict"):
        await ctx.device.tune("art", data=[1, 2])
    with pytest.raises(ValueError, match="named by a string"):
        await ctx.device.tune("art", piece=7)

    assert ctx.device.rotation == 30
    assert ctx.device.channel == "hold"


@pytest.mark.asyncio
async def test_adjusting_redraws_the_channel_that_uses_the_control(tmp_path, channels):
    ctx = await started(tmp_path)
    await ctx.device.tune("message", message="ONE")

    await ctx.device.adjust(message="TWO")

    assert ctx.board.sent == ["ONE", "TWO"]


@pytest.mark.asyncio
async def test_adjusting_leaves_a_channel_that_does_not_use_it(tmp_path, channels):
    ctx = await started(tmp_path)
    await ctx.device.tune("message", message="ONE")

    await ctx.device.adjust(piece="rainbow", rotation=0)

    assert ctx.board.sent == ["ONE"]
    assert ctx.board.grids == []
    # But the change is kept, for when the channel that uses it comes up.
    await ctx.device.tune("art")
    assert ctx.board.grids == ["rainbow"]


@pytest.mark.asyncio
async def test_data_is_kept_per_channel(tmp_path, channels):
    ctx = await started(tmp_path)

    await ctx.device.tune("art", data={"today": 3})
    await ctx.device.tune("message", data={"text": "x"})

    assert ctx.device.data_for("art") == {"today": 3}
    assert ctx.device.data_for("message") == {"text": "x"}
    assert ctx.device.data_for("hold") == {}


@pytest.mark.asyncio
async def test_a_failing_channel_is_logged_and_showing_stays(tmp_path, channels, caplog):
    ctx = await started(tmp_path)
    await ctx.device.tune("message", message="ONE")

    await ctx.device.tune("boom")

    assert "channel boom failed" in caplog.text
    assert ctx.device.channel == "boom"
    assert ctx.device.showing == "Message: ONE"


# -- drawing ------------------------------------------------------------------


class SlowBoard(FakeBoard):
    """A board that takes its time, as the real one does every fifteen seconds."""

    def __init__(self):
        super().__init__()
        self.gate = asyncio.Event()

    async def send_text(self, text):
        await self.gate.wait()
        self.sent.append(text)


@pytest.mark.asyncio
async def test_a_newer_draw_takes_the_place_of_one_still_waiting(tmp_path, channels):
    board = SlowBoard()
    ctx = await started(tmp_path, board)

    first = asyncio.create_task(ctx.device.tune("message", message="ONE"))
    await asyncio.sleep(0)
    second = asyncio.create_task(ctx.device.adjust(message="TWO"))
    await asyncio.sleep(0)
    board.gate.set()
    await asyncio.gather(first, second)

    # ONE never went out: TWO is what the board shows, and the only draw.
    assert board.sent == ["TWO"]
    assert ctx.device.showing == "Message: TWO"


@pytest.mark.asyncio
async def test_a_change_is_published_before_the_board_has_it(tmp_path, channels):
    board = SlowBoard()
    ctx = await started(tmp_path, board)
    broker = Recorder()
    await ctx.device.connected(broker)

    drawing = asyncio.create_task(ctx.device.tune("message", message="SOON"))
    await asyncio.sleep(0)

    assert broker.last(state_topic("channel")) == "Message"
    assert broker.last(state_topic("message")) == "SOON"
    assert board.sent == []
    board.gate.set()
    await drawing
    assert broker.last(state_topic("showing")) == "Message: SOON"


@pytest.mark.asyncio
async def test_commands_are_seen_to_off_the_message_loop(tmp_path, channels):
    board = SlowBoard()
    ctx = await started(tmp_path, board)

    # Neither of these waits on the board, so the second is not stuck behind
    # the first; and the second is the one that wins.
    await ctx.device.received(command_topic("channel"), "Message")
    await ctx.device.received(command_topic("message"), "LATER")
    for _ in range(5):
        await asyncio.sleep(0)
    assert ctx.device.channel == "message"
    assert ctx.device.message == "LATER"
    assert board.sent == []

    board.gate.set()
    await ctx.device.settled()

    assert board.sent == ["LATER"]


@pytest.mark.asyncio
async def test_stopping_drops_the_draw_going_out(tmp_path, channels):
    board = SlowBoard()
    ctx = await started(tmp_path, board)
    drawing = asyncio.create_task(ctx.device.tune("message", message="NEVER"))
    await asyncio.sleep(0)

    ctx.device.stop()
    await ctx.device.settled()
    board.gate.set()
    await drawing

    assert board.sent == []


@pytest.mark.asyncio
async def test_being_cancelled_while_drawing_is_still_being_cancelled(
    tmp_path, channels
):
    board = SlowBoard()
    ctx = await started(tmp_path, board)
    drawing = asyncio.create_task(ctx.device.tune("message", message="NEVER"))
    await asyncio.sleep(0)

    drawing.cancel()

    with pytest.raises(asyncio.CancelledError):
        await drawing


# -- rotation -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_channel_can_ask_to_be_drawn_again(tmp_path, channels):
    ctx = await started(tmp_path)

    await ctx.device.tune("art")
    await settle()

    assert len(ctx.board.grids) >= 2
    ctx.device.stop()


@pytest.mark.asyncio
async def test_any_draw_in_the_meantime_cancels_the_redraw(tmp_path, channels):
    ctx = await started(tmp_path)
    await ctx.device.tune("art")

    await ctx.device.tune("hold")
    drawn = len(ctx.board.grids)
    await settle()

    assert len(ctx.board.grids) == drawn


@pytest.mark.asyncio
async def test_stopping_cancels_the_redraw(tmp_path, channels):
    ctx = await started(tmp_path)
    await ctx.device.tune("art")

    ctx.device.stop()
    drawn = len(ctx.board.grids)
    await settle()

    assert len(ctx.board.grids) == drawn


# -- the buttons --------------------------------------------------------------


@pytest.mark.asyncio
async def test_next_piece_tunes_to_the_channel_that_shows_pieces(tmp_path, channels):
    ctx = await started(tmp_path)
    await ctx.device.adjust(piece="rainbow", rotation=0)

    await ctx.device.next_piece()

    assert ctx.device.channel == "art"
    assert ctx.device.piece is None
    assert ctx.board.grids == ["random"]


@pytest.mark.asyncio
async def test_next_piece_with_nothing_showing_pieces_says_so(
    tmp_path, monkeypatch, caplog
):
    monkeypatch.setattr(registry, "CHANNELS", [])

    @registry.channel("hold", label="Hold")
    async def hold(ctx):
        return None

    ctx = await started(tmp_path)

    await ctx.device.next_piece()

    assert "no channel shows pieces" in caplog.text
    assert ctx.device.channel == "hold"


@pytest.mark.asyncio
async def test_capture_saves_the_board_as_a_piece(tmp_path, channels):
    board = FakeBoard(art.to_grid(art.ARTWORKS["rainbow"]))
    ctx = await started(tmp_path, board)

    await ctx.device.capture()

    assert "capture-1" in ctx.art.saved()


@pytest.mark.asyncio
async def test_a_capture_that_cannot_be_made_is_a_warning(tmp_path, channels, caplog):
    ctx = await started(tmp_path, FakeBoard(error=BoardError("no API token configured")))
    await ctx.device.capture()
    assert "could not capture the board: no API token" in caplog.text

    ctx = await started(tmp_path, FakeBoard(charcodes.blank_grid()))
    await ctx.device.capture()
    assert "the board is blank" in caplog.text

    assert ctx.art.saved() == {}


# -- the broker ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_connecting_describes_the_device_and_says_how_it_stands(tmp_path, channels):
    ctx = await started(tmp_path)
    broker = Recorder()

    await ctx.device.connected(broker)

    assert (DISCOVERY_TOPIC, broker.last(DISCOVERY_TOPIC), True) in broker.messages
    assert (AVAILABILITY_TOPIC, "online", True) in broker.messages
    assert broker.last(state_topic("channel")) == "Hold"
    assert broker.last(state_topic("piece")) == "Random"
    assert broker.last(state_topic("message")) == ""
    assert broker.last(state_topic("rotation")) == "30"
    assert broker.last(state_topic("showing")) == "Hold"
    # Every state is retained, so Home Assistant has it whenever it looks.
    assert all(retain for topic, _, retain in broker.messages)


@pytest.mark.asyncio
async def test_the_description_is_sent_once_until_it_changes(tmp_path, channels):
    ctx = await started(tmp_path)
    broker = Recorder()
    await ctx.device.connected(broker)

    await ctx.device.announce()

    assert len(broker.on(DISCOVERY_TOPIC)) == 1
    assert len(broker.on(AVAILABILITY_TOPIC)) == 2


@pytest.mark.asyncio
async def test_a_new_connection_gets_the_description_again(tmp_path, channels):
    ctx = await started(tmp_path)
    broker = Recorder()
    await ctx.device.connected(broker)
    await ctx.device.disconnected()

    await ctx.device.connected(broker)

    assert len(broker.on(DISCOVERY_TOPIC)) == 2


@pytest.mark.asyncio
async def test_a_change_is_published_as_it_happens(tmp_path, channels):
    ctx = await started(tmp_path)
    broker = Recorder()
    await ctx.device.connected(broker)

    await ctx.device.tune("art", piece="rainbow")
    await ctx.device.adjust(rotation=5)

    assert broker.last(state_topic("channel")) == "Art"
    assert broker.last(state_topic("piece")) == "rainbow"
    assert broker.last(state_topic("showing")) == "Art: rainbow"
    assert broker.last(state_topic("rotation")) == "5"


@pytest.mark.asyncio
async def test_a_new_piece_in_the_library_changes_the_description(tmp_path, channels):
    board = FakeBoard(art.to_grid(art.ARTWORKS["rainbow"]))
    ctx = await started(tmp_path, board)
    broker = Recorder()
    await ctx.device.connected(broker)

    await ctx.device.capture()

    piece = broker.description()["components"]["piece"]
    assert piece["options"] == ["Random", "rainbow", "capture-1"]
    assert len(broker.on(DISCOVERY_TOPIC)) == 2


@pytest.mark.asyncio
async def test_a_piece_deleted_from_the_library_goes_back_to_random(tmp_path, channels):
    ctx = await started(tmp_path)
    ctx.art.directory.mkdir()
    (ctx.art.directory / "sunrise.txt").write_text(art.ARTWORKS["rainbow"])
    await ctx.device.tune("message", piece="sunrise", message="HI")
    broker = Recorder()
    await ctx.device.connected(broker)

    ctx.art.delete("sunrise")
    await ctx.device.library_changed()

    # Not an option any more, so not a state the select could show.
    assert ctx.device.piece is None
    assert broker.last(state_topic("piece")) == "Random"
    assert "sunrise" not in broker.description()["components"]["piece"]["options"]
    # And the channel up was not the one showing pieces, so it was left alone.
    assert ctx.board.sent == ["HI"]


@pytest.mark.asyncio
async def test_a_piece_deleted_while_the_app_was_down_goes_back_to_random(
    tmp_path, channels
):
    State(channel="hold", piece="sunrise").save(tmp_path / "device.json")

    ctx = await started(tmp_path)

    assert ctx.device.piece is None
    assert json.loads((tmp_path / "device.json").read_text())["piece"] is None


@pytest.mark.asyncio
async def test_off_the_broker_nothing_is_published_and_nothing_breaks(tmp_path, channels):
    ctx = await started(tmp_path)
    broker = Recorder()
    await ctx.device.connected(broker)
    await ctx.device.disconnected()
    sent = len(broker.messages)

    await ctx.device.tune("message", message="HI")
    await ctx.device.announce()

    assert len(broker.messages) == sent
    assert ctx.board.sent == ["HI"]


@pytest.mark.asyncio
async def test_home_assistant_coming_back_is_told_everything_again(tmp_path, channels):
    ctx = await started(tmp_path)
    broker = Recorder()
    await ctx.device.connected(broker)

    await ctx.device.received(STATUS_TOPIC, "offline")
    assert len(broker.on(DISCOVERY_TOPIC)) == 1

    await ctx.device.received(STATUS_TOPIC, "online")
    assert len(broker.on(DISCOVERY_TOPIC)) == 2
    assert broker.on(state_topic("channel")) == ["Hold", "Hold"]


# -- the commands -------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_channel_select_tunes_by_label(tmp_path, channels):
    ctx = await started(tmp_path)

    await ctx.device.received(command_topic("channel"), "Art")
    await ctx.device.settled()

    assert ctx.device.channel == "art"
    assert ctx.board.grids == ["random"]
    ctx.device.stop()


@pytest.mark.asyncio
async def test_a_channel_that_is_not_an_option_is_ignored(tmp_path, channels, caplog):
    ctx = await started(tmp_path)

    await ctx.device.received(command_topic("channel"), "Weather")
    await ctx.device.settled()

    assert ctx.device.channel == "hold"
    assert "ignoring channel 'Weather': there is no such channel" in caplog.text


@pytest.mark.asyncio
async def test_the_piece_select_names_a_piece_or_random(tmp_path, channels):
    ctx = await started(tmp_path)

    await ctx.device.received(command_topic("piece"), "rainbow")
    await ctx.device.settled()
    assert ctx.device.piece == "rainbow"

    await ctx.device.received(command_topic("piece"), "Random")
    await ctx.device.settled()
    assert ctx.device.piece is None


@pytest.mark.asyncio
async def test_the_message_text_sets_the_message(tmp_path, channels):
    ctx = await started(tmp_path)

    await ctx.device.received(command_topic("message"), "BACK SOON")
    await ctx.device.settled()

    assert ctx.device.message == "BACK SOON"


@pytest.mark.asyncio
async def test_the_rotation_number_arrives_with_decimals(tmp_path, channels):
    ctx = await started(tmp_path)

    await ctx.device.received(command_topic("rotation"), "45.0")
    await ctx.device.settled()

    assert ctx.device.rotation == 45


@pytest.mark.asyncio
async def test_a_rotation_that_is_not_a_number_is_ignored(tmp_path, channels, caplog):
    ctx = await started(tmp_path)

    await ctx.device.received(command_topic("rotation"), "soon")
    await ctx.device.settled()

    assert ctx.device.rotation == 30
    assert "ignoring rotation 'soon'" in caplog.text


@pytest.mark.asyncio
async def test_the_buttons_press(tmp_path, channels):
    board = FakeBoard(art.to_grid(art.ARTWORKS["rainbow"]))
    ctx = await started(tmp_path, board)
    await ctx.device.adjust(rotation=0)

    await ctx.device.received(command_topic("next"), "PRESS")
    await ctx.device.settled()
    assert ctx.board.grids == ["random"]

    await ctx.device.received(command_topic("capture"), "PRESS")
    await ctx.device.settled()
    assert "capture-1" in ctx.art.saved()


@pytest.mark.asyncio
async def test_a_control_we_do_not_have_is_a_warning(tmp_path, channels, caplog):
    ctx = await started(tmp_path)

    await ctx.device.received(command_topic("volume"), "11")
    await ctx.device.settled()

    assert "no control named volume" in caplog.text


@pytest.mark.asyncio
async def test_other_topics_are_not_ours(tmp_path, channels):
    ctx = await started(tmp_path)

    await ctx.device.received("vestaboard/channel", "Art")
    await ctx.device.received("somebody/else/set", "Art")
    await ctx.device.received("vestaboard//set", "Art")

    assert ctx.device.channel == "hold"


def test_which_control_a_command_topic_is_for():
    assert control_of("vestaboard/channel/set") == "channel"
    assert control_of("vestaboard/channel") is None
    assert control_of("vestaboard//set") is None
    assert control_of("other/channel/set") is None
    assert control_of("vestaboard/a/b/set") is None


# -- the description ----------------------------------------------------------


@pytest.mark.asyncio
async def test_the_description_is_one_device_with_every_control_on_it(tmp_path, channels):
    ctx = await started(tmp_path)

    description = ctx.device.discovery()

    assert description["device"] == {
        "identifiers": ["vestaboard"],
        "name": "Vestaboard",
        "manufacturer": "Vestaboard",
        "model": "Note",
    }
    assert description["origin"]["name"] == "vestaboard"
    assert description["availability_topic"] == AVAILABILITY_TOPIC

    components = description["components"]
    assert {name: c["platform"] for name, c in components.items()} == {
        "channel": "select",
        "piece": "select",
        "message": "text",
        "rotation": "number",
        "next": "button",
        "capture": "button",
        "showing": "sensor",
    }
    # Home Assistant tells entities apart by these, so they had better differ.
    ids = [c["unique_id"] for c in components.values()]
    assert len(set(ids)) == len(ids)
    assert all(uid.startswith("vestaboard_") for uid in ids)


@pytest.mark.asyncio
async def test_the_selects_offer_the_channels_and_the_pieces(tmp_path, channels):
    ctx = await started(tmp_path)

    components = ctx.device.discovery()["components"]

    assert components["channel"]["options"] == ["Hold", "Art", "Message", "Boom"]
    assert components["piece"]["options"] == ["Random", "rainbow"]


@pytest.mark.asyncio
async def test_each_control_is_on_its_own_topics(tmp_path, channels):
    ctx = await started(tmp_path)

    components = ctx.device.discovery()["components"]

    assert components["channel"]["state_topic"] == "vestaboard/channel"
    assert components["channel"]["command_topic"] == "vestaboard/channel/set"
    # A button has nothing to report, and a sensor nothing to be told.
    assert "state_topic" not in components["next"]
    assert "command_topic" not in components["showing"]


@pytest.mark.asyncio
async def test_the_rotation_is_a_number_of_minutes(tmp_path, channels):
    ctx = await started(tmp_path)

    rotation = ctx.device.discovery()["components"]["rotation"]

    assert rotation["unit_of_measurement"] == "min"
    assert rotation["min"] == 0
    assert rotation["step"] == 1


def test_what_supervisor_knows_goes_on_the_device(tmp_path, channels):
    device = Device(
        tmp_path / "device.json",
        Identity(version="0.2.0", configuration_url="homeassistant://hassio/ingress/x"),
    )

    described = device.discovery()["device"]

    assert described["sw_version"] == "0.2.0"
    assert described["configuration_url"] == "homeassistant://hassio/ingress/x"


def test_a_device_that_knows_nothing_of_itself_says_nothing(tmp_path, channels):
    described = Device(tmp_path / "device.json").discovery()["device"]

    assert "sw_version" not in described
    assert "configuration_url" not in described


def test_a_piece_called_random_is_not_offered_twice(tmp_path, channels):
    # Random is the select's own option; a piece by that name would be
    # indistinguishable from it, so it is left off rather than doubled.
    device = Device(tmp_path / "device.json")
    ctx = FakeContext(tmp_path)
    ctx.art.directory.mkdir()
    piece = ctx.art.directory / f"{device_module.RANDOM}.txt"
    piece.write_text(art.ARTWORKS["rainbow"])
    device._ctx = ctx

    options = device.discovery()["components"]["piece"]["options"]

    assert options.count(device_module.RANDOM) == 1
