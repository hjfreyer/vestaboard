"""The board as Home Assistant sees it: a device, with a channel dial on it.

Home Assistant cannot see an app. It can see a device, if an integration tells
it about one, and MQTT discovery is the integration that takes a description
from anything on the broker. So the app describes the board as a device with a
few controls on it, and from then on the board is a thing in the house rather
than an app to go and find:

* **Channel**, a select. What the board is showing: one of the channels that
  ``rules.py`` declares with ``@channel``. Change it on the device page, or
  from an automation with ``select.select_option``, on a clock or on anything
  else Home Assistant can trigger on.
* **Piece**, a select: a named piece of art, or ``Random``.
* **Art rotation**, a number: how often, in minutes, a random piece changes.
* **Message**, a text: what the Message channel says.
* **Next piece** and **Capture the board**, buttons.
* **Showing**, a sensor saying what the board has on it.

The controls are the device's state, and it is Home Assistant that changes
them; this side only keeps a copy, in ``/data/device.json``, so that a restart
comes back on the same channel. Every change is published to a retained topic,
so what Home Assistant shows is what the app believes.

The board itself always shows the current channel. Changing the channel draws
it; changing a control the current channel draws from redraws it; an action
fired from an automation sets a control or two and tunes, so the select agrees
with the board afterwards. Nothing here draws unasked.

A change takes effect at once, and the drawing follows: the board takes one
message every fifteen seconds, so a draw can be a while going out, and a
newer one in the meantime takes its place rather than queueing behind it. The
board ends up showing the latest thing asked for, and Home Assistant hears
about each change as it is made rather than as it lands.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import registry
from .board import BoardError

if TYPE_CHECKING:
    from .app import Context

_LOGGER = logging.getLogger(__name__)

#: How the device gets a message onto the broker: ``(topic, payload, retain=)``.
Publish = Callable[..., Awaitable[None]]

#: Our topics all start here, so ``vestaboard/channel`` holds the channel and
#: ``vestaboard/channel/set`` is where Home Assistant asks for another one.
PREFIX = "vestaboard"

#: Where Home Assistant looks for a device that describes itself. One payload
#: for the whole device, every control in it, at the discovery prefix Home
#: Assistant uses unless told otherwise.
DISCOVERY_TOPIC = f"homeassistant/device/{PREFIX}/config"

#: Home Assistant says ``online`` here when it starts, which is our cue to
#: describe the device again: it may have forgotten.
STATUS_TOPIC = "homeassistant/status"

#: ``online`` while we are here; the broker says ``offline`` for us if we go
#: without a word, and the device shows as unavailable rather than stale.
AVAILABILITY_TOPIC = f"{PREFIX}/availability"

#: The Piece select's option for no piece in particular.
RANDOM = "Random"

#: Where a device that has never been told anything starts: leaving the board
#: alone, so an update does not change what is on it until somebody asks.
DEFAULT_CHANNEL = "hold"
DEFAULT_ROTATION = 30

#: Everything with a state topic, in the order it is published.
STATES = ("channel", "piece", "message", "rotation", "showing")

REPOSITORY = "https://github.com/hjfreyer/vestaboard"


def state_topic(control: str) -> str:
    return f"{PREFIX}/{control}"


def command_topic(control: str) -> str:
    return f"{PREFIX}/{control}/set"


def control_of(topic: str) -> str | None:
    """Which control a command topic is for, or None for any other topic."""
    parts = topic.split("/")
    if len(parts) == 3 and parts[0] == PREFIX and parts[2] == "set" and parts[1]:
        return parts[1]
    return None


@dataclass(frozen=True)
class Identity:
    """What the device says about itself beyond its name."""

    version: str | None = None
    #: Where the device page's link goes: the gallery, through ingress.
    configuration_url: str | None = None


@dataclass
class State:
    """The controls, as last set. This is what ``/data/device.json`` holds."""

    channel: str = DEFAULT_CHANNEL
    piece: str | None = None
    message: str = ""
    rotation: int = DEFAULT_ROTATION
    #: What an action last handed each channel: the egg numbers, say.
    data: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> State:
        """The saved state, or a fresh one if there is none or it is unreadable.

        Field by field, so that a file written by an older version of the app,
        or hand-edited into something odd, costs the odd field and not the lot.
        """
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError) as exc:
            _LOGGER.warning("ignoring %s, which does not parse: %s", path, exc)
            return cls()
        if not isinstance(raw, dict):
            _LOGGER.warning("ignoring %s, which is not a device state", path)
            return cls()

        state = cls()
        if isinstance(raw.get("channel"), str):
            state.channel = raw["channel"]
        if isinstance(raw.get("piece"), str):
            state.piece = raw["piece"]
        if isinstance(raw.get("message"), str):
            state.message = raw["message"]
        if isinstance(raw.get("rotation"), int) and raw["rotation"] >= 0:
            state.rotation = raw["rotation"]
        if isinstance(raw.get("data"), dict):
            state.data = {
                name: dict(value)
                for name, value in raw["data"].items()
                if isinstance(value, dict)
            }
        return state

    def save(self, path: Path) -> None:
        """Write the state out. Failing to is worth a line, not the board."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            _LOGGER.warning("could not save the device state to %s: %s", path, exc)


class Device:
    """The device: its controls, what they do to the board, and the broker."""

    def __init__(self, state_path: Path, identity: Identity | None = None) -> None:
        self._path = state_path
        self.state = State.load(state_path)
        self.identity = identity or Identity()
        self._ctx: Context | None = None
        self._publish: Publish | None = None
        #: The description last sent, so a change to it -- a new piece in the
        #: library, say -- is the only thing that sends another.
        self._announced: str | None = None
        self._showing: str | None = None
        #: The draw going out, if one is; a newer one takes its place.
        self._drawing: asyncio.Task[None] | None = None
        #: A redraw a channel asked for, waiting its turn.
        self._redraw: asyncio.Task[None] | None = None
        #: Commands from the broker being seen to, off the message loop.
        self._handling: set[asyncio.Task[None]] = set()

    # -- the controls, for the channels to read ------------------------------

    @property
    def channel(self) -> str:
        return self.state.channel

    @property
    def piece(self) -> str | None:
        """The piece the Piece select names, or None for a random one."""
        return self.state.piece

    @property
    def message(self) -> str:
        return self.state.message

    @property
    def rotation(self) -> int:
        """Minutes between random pieces; 0 leaves the piece up."""
        return self.state.rotation

    def data_for(self, channel: str) -> dict[str, Any]:
        """What an action last handed the channel, or ``{}``."""
        return dict(self.state.data.get(channel, {}))

    @property
    def showing(self) -> str | None:
        """What the board has on it, as the Showing sensor says it."""
        return self._showing

    # -- what changes the board ---------------------------------------------

    async def start(self, ctx: Context) -> None:
        """Take the context the channels need, and put the channel up."""
        self._ctx = ctx
        if self._current() is None:
            _LOGGER.warning(
                "no channel named %r any more; holding instead", self.state.channel
            )
            self.state.channel = DEFAULT_CHANNEL
            self.state.save(self._path)
        await self._forget_a_missing_piece()
        await self.draw()

    async def tune(self, channel: str, **controls: Any) -> None:
        """Switch the board to a channel, setting any controls first.

        This is what an action does: ``tune("message", message="DINNER")``
        says it and leaves the Channel select reading Message. A control that
        will not take its value is an error, and the board is left alone.
        """
        if registry.channel_named(channel) is None:
            raise ValueError(f"no channel named {channel!r}")
        self._apply(controls, for_channel=channel)
        self.state.channel = channel
        self.state.save(self._path)
        await self._publish_states("channel", *controls)
        await self.draw()

    async def adjust(self, **controls: Any) -> None:
        """Change controls without changing channel, as the device page does.

        The channel that is up is redrawn if it draws from one of them; any
        other channel is left as it is, and sees the change when it is next
        tuned to.
        """
        self._apply(controls, for_channel=None)
        self.state.save(self._path)
        await self._publish_states(*controls)
        current = self._current()
        if current is not None and current.uses & controls.keys():
            await self.draw()

    def _apply(self, controls: dict[str, Any], *, for_channel: str | None) -> None:
        for name, value in controls.items():
            if name == "piece":
                if value is not None and not isinstance(value, str):
                    raise ValueError(f"a piece is named by a string, not {value!r}")
                pieces = self._ctx.art.pieces() if self._ctx is not None else None
                if value and pieces is not None and value not in pieces:
                    known = ", ".join(sorted(pieces))
                    raise ValueError(f"no piece named {value!r}; there is {known}")
                self.state.piece = value or None
            elif name == "message":
                self.state.message = "" if value is None else str(value)
            elif name == "rotation":
                minutes = int(value)
                if minutes < 0:
                    raise ValueError(f"rotation cannot be {minutes} minutes")
                self.state.rotation = minutes
            elif name == "data":
                if for_channel is None:
                    raise ValueError("data belongs to a channel; tune to one with it")
                if not isinstance(value, dict):
                    raise ValueError(f"a channel's data is a dict, not {value!r}")
                self.state.data[for_channel] = dict(value)
            else:
                raise ValueError(f"no control named {name!r}")

    async def draw(self) -> None:
        """Put the current channel on the board, and wait for it to be up.

        Unless a newer draw takes over in the meantime: then this one is
        dropped, since what the board should show has moved on, and this
        returns quietly to whoever asked.
        """
        task = self.request_draw()
        try:
            await task
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise
            # Superseded, not cancelled: the later draw is the board's.

    def request_draw(self) -> asyncio.Task[None]:
        """Start drawing the current channel, in place of any draw still waiting."""
        self._cancel_redraw()
        drawing = self._drawing
        if drawing is not None and not drawing.done():
            if drawing is asyncio.current_task():
                raise RuntimeError("a channel cannot ask to be drawn while drawing")
            drawing.cancel()
        self._drawing = asyncio.create_task(self._draw_now())
        return self._drawing

    async def _draw_now(self) -> None:
        """The drawing itself: the channel's function, then the Showing sensor.

        A channel that fails is logged and the board left as it was; the
        Showing sensor keeps saying what it said, which is still what shows.
        """
        current = self._current()
        if current is None or self._ctx is None:
            return
        try:
            drew = await current.fn(self._ctx)
        except Exception:
            _LOGGER.exception("channel %s failed", current.name)
            return
        self._showing = f"{current.label}: {drew}" if drew else current.label
        await self._publish_states("showing")

    async def settled(self) -> None:
        """Wait until nothing is in hand: no command being seen to, no draw out."""
        while True:
            pending = set(self._handling)
            if self._drawing is not None and not self._drawing.done():
                pending.add(self._drawing)
            if not pending:
                return
            await asyncio.wait(pending)

    def redraw_in(self, seconds: float) -> None:
        """Draw the channel again in a while -- unless something draws first.

        A channel that rotates calls this from its own drawing: the art, with
        the rotation in minutes. Any draw in the meantime, a channel change or
        a control changing, cancels it, since that draw starts a new interval
        of its own.
        """
        self._cancel_redraw()
        self._redraw = asyncio.create_task(self._redraw_later(seconds))

    async def _redraw_later(self, seconds: float) -> None:
        await asyncio.sleep(seconds)
        self._redraw = None
        await self.draw()

    def stop(self) -> None:
        """Drop whatever is in hand, as when the app is going down."""
        self._cancel_redraw()
        if self._drawing is not None:
            self._drawing.cancel()
        for task in self._handling:
            task.cancel()

    def _cancel_redraw(self) -> None:
        task, self._redraw = self._redraw, None
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    async def next_piece(self) -> None:
        """Another random piece, on whichever channel shows pieces."""
        channel = self._current()
        if channel is None or "piece" not in channel.uses:
            channel = next((ch for ch in registry.CHANNELS if "piece" in ch.uses), None)
        if channel is None:
            _LOGGER.warning("no channel shows pieces, so there is no next one")
            return
        await self.tune(channel.name, piece=None)

    async def capture(self) -> None:
        """Save what the board is showing as a new piece, as the gallery does."""
        if self._ctx is None:
            return
        try:
            saved = self._ctx.art.capture(await self._ctx.board.read())
        except (BoardError, ValueError, OSError) as exc:
            _LOGGER.warning("could not capture the board: %s", exc)
            return
        if not saved.is_new:
            _LOGGER.info("the board is already saved as %s", saved.name)
        await self.library_changed()

    def _current(self) -> registry.Channel | None:
        return registry.channel_named(self.state.channel)

    # -- the broker ----------------------------------------------------------

    async def connected(self, publish: Publish) -> None:
        """We are on the broker: describe the device, and say how it stands."""
        self._publish = publish
        # A new connection could be to a broker that has never heard of us.
        self._announced = None
        await self.announce()

    async def disconnected(self) -> None:
        self._publish = None

    async def received(self, topic: str, payload: str) -> None:
        """A message from the broker: a command, or Home Assistant starting."""
        if topic == STATUS_TOPIC:
            if payload == "online":
                # The description is retained on the broker, so Home Assistant
                # has it; but saying it again costs nothing and covers a
                # broker that lost it.
                _LOGGER.info("Home Assistant is back; describing the device again")
                self._announced = None
                await self.announce()
            return

        control = control_of(topic)
        if control is None:
            return
        _LOGGER.info("%s <- %r", control, payload)
        # Seen to on its own, so a command that ends up waiting on the board
        # does not hold up the ones behind it -- the last of which is the
        # one that should win.
        task = asyncio.create_task(self._handle(control, payload))
        self._handling.add(task)
        task.add_done_callback(self._handling.discard)

    async def _handle(self, control: str, payload: str) -> None:
        try:
            await self._command(control, payload)
        except ValueError as exc:
            _LOGGER.warning("ignoring %s %r: %s", control, payload, exc)
        except Exception:
            _LOGGER.exception("%s %r failed", control, payload)

    async def _command(self, control: str, payload: str) -> None:
        if control == "channel":
            target = registry.channel_labelled(payload)
            if target is None:
                raise ValueError("there is no such channel")
            await self.tune(target.name)
        elif control == "piece":
            await self.adjust(piece=None if payload == RANDOM else payload)
        elif control == "message":
            await self.adjust(message=payload)
        elif control == "rotation":
            # Home Assistant sends a number as it has it, decimals and all.
            await self.adjust(rotation=int(float(payload)))
        elif control == "next":
            await self.next_piece()
        elif control == "capture":
            await self.capture()
        else:
            _LOGGER.warning("no control named %s", control)

    async def library_changed(self) -> None:
        """The Piece options follow the library, so describe the device again."""
        await self._forget_a_missing_piece()
        await self.announce()

    async def _forget_a_missing_piece(self) -> None:
        """A piece that has gone from the library goes back to Random.

        The Piece select only knows the options it was given, so a name that is
        no longer one of them would be a state Home Assistant cannot show.
        """
        name = self.state.piece
        if name is None or self._ctx is None or name in self._ctx.art.pieces():
            return
        _LOGGER.warning("no piece named %r any more; back to %s", name, RANDOM)
        self.state.piece = None
        self.state.save(self._path)
        await self._publish_states("piece")

    async def announce(self) -> None:
        """Describe the device, if the description changed, and publish it all."""
        if self._publish is None:
            return
        description = json.dumps(self.discovery(), sort_keys=True)
        if description != self._announced:
            await self._publish(DISCOVERY_TOPIC, description, retain=True)
            self._announced = description
        await self._publish(AVAILABILITY_TOPIC, "online", retain=True)
        await self._publish_states(*STATES)

    async def _publish_states(self, *names: str) -> None:
        if self._publish is None:
            return
        for name in names:
            if name in STATES:
                await self._publish(state_topic(name), self._state_of(name), retain=True)

    def _state_of(self, name: str) -> str:
        """A control's state as its topic carries it: what its entity shows."""
        current = self._current()
        if name == "channel":
            return current.label if current is not None else self.state.channel
        if name == "piece":
            return self.state.piece or RANDOM
        if name == "message":
            return self.state.message
        if name == "rotation":
            return str(self.state.rotation)
        if name == "showing":
            if self._showing is not None:
                return self._showing
            return current.label if current is not None else ""
        raise ValueError(f"{name} has no state")

    def discovery(self) -> dict[str, Any]:
        """The device, every control on it, as MQTT discovery wants it said."""
        pieces = list(self._ctx.art.pieces()) if self._ctx is not None else []
        device: dict[str, Any] = {
            "identifiers": [PREFIX],
            "name": "Vestaboard",
            "manufacturer": "Vestaboard",
            "model": "Note",
        }
        if self.identity.version:
            device["sw_version"] = self.identity.version
        if self.identity.configuration_url:
            device["configuration_url"] = self.identity.configuration_url

        return {
            "device": device,
            "origin": {"name": "vestaboard", "url": REPOSITORY},
            # Shared by every component: the device is there, or it is not.
            "availability_topic": AVAILABILITY_TOPIC,
            "components": {
                "channel": _component(
                    "select",
                    "channel",
                    "Channel",
                    "mdi:television-guide",
                    options=[ch.label for ch in registry.CHANNELS],
                ),
                "piece": _component(
                    "select",
                    "piece",
                    "Piece",
                    "mdi:palette",
                    options=[RANDOM, *(name for name in pieces if name != RANDOM)],
                ),
                "message": _component("text", "message", "Message", "mdi:message-text"),
                "rotation": _component(
                    "number",
                    "rotation",
                    "Art rotation",
                    "mdi:timer-refresh-outline",
                    min=0,
                    max=24 * 60,
                    step=1,
                    unit_of_measurement="min",
                    mode="box",
                ),
                "next": _component(
                    "button", "next", "Next piece", "mdi:skip-next", state=False
                ),
                "capture": _component(
                    "button", "capture", "Capture the board", "mdi:camera", state=False
                ),
                "showing": _component(
                    "sensor", "showing", "Showing", "mdi:television-play", command=False
                ),
            },
        }


def _component(
    platform: str,
    control: str,
    name: str,
    icon: str,
    *,
    state: bool = True,
    command: bool = True,
    **extra: Any,
) -> dict[str, Any]:
    """One entity of the device, on the topics its control uses."""
    component: dict[str, Any] = {
        "platform": platform,
        "name": name,
        "unique_id": f"{PREFIX}_{control}",
        "icon": icon,
    }
    if state:
        component["state_topic"] = state_topic(control)
    if command:
        component["command_topic"] = command_topic(control)
    component.update(extra)
    return component
