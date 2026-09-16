"""The decorators rules.py uses to say what the board can show and when."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .app import Context

ActionFn = Callable[["Context", dict[str, Any]], Awaitable[None]]
ChannelFn = Callable[["Context"], Awaitable[str | None]]

#: Actions are Home Assistant events under our own name, so that an automation
#: firing ``vestaboard_show_art`` cannot collide with anything else.
ACTION_PREFIX = "vestaboard_"


def action_event_type(action: str) -> str:
    """Event type Home Assistant fires to run the named action."""
    return f"{ACTION_PREFIX}{action}"


@dataclass(frozen=True)
class ActionRule:
    name: str
    fn: ActionFn
    action: str

    @property
    def event_type(self) -> str:
        return action_event_type(self.action)


ACTION_RULES: list[ActionRule] = []


def on_action(action: str) -> Callable[[ActionFn], ActionFn]:
    """Run when Home Assistant asks for it.

    An app cannot register a real service, so an action is a custom event:
    ``@on_action("show_art")`` runs whenever something in Home Assistant fires
    ``vestaboard_show_art``. In an automation that is the **Fire event** action:

        actions:
          - event: vestaboard_show_art
            event_data:
              name: rainbow

    The rule is handed the event data, so ``event_data`` is how an automation
    passes arguments; it is ``{}`` when the automation sends none.

    The actions shipped are the device's remote control: each one sets a
    control or two and tunes the board to a channel, so an automation that
    fires one gets what it asked for on the board, and the device's Channel
    select agrees with what it sees.
    """

    def decorator(fn: ActionFn) -> ActionFn:
        ACTION_RULES.append(ActionRule(name=fn.__name__, fn=fn, action=action))
        return fn

    return decorator


@dataclass(frozen=True)
class Channel:
    """Something the board can be tuned to.

    ``uses`` names the device controls the channel draws from -- ``piece`` and
    ``rotation`` for the art, say -- so that changing one of them in Home
    Assistant redraws the channel that is showing it, and leaves any other
    channel alone.
    """

    name: str
    label: str
    fn: ChannelFn
    uses: frozenset[str] = frozenset()


CHANNELS: list[Channel] = []


def channel(
    name: str, *, label: str | None = None, uses: tuple[str, ...] = ()
) -> Callable[[ChannelFn], ChannelFn]:
    """Declare a channel: something the board shows until it is tuned away.

    The device Home Assistant sees has a Channel select whose options are the
    labels declared here, in this order. Picking one -- by hand on the device
    page, or from an automation with ``select.select_option`` on a schedule --
    runs the function, which draws the board from whatever the device's
    controls hold and returns a word or two on what it drew, for the Showing
    sensor. It runs again whenever a control in ``uses`` changes while the
    channel is tuned, and whenever it asked to be, with ``ctx.device.redraw_in``.
    """

    def decorator(fn: ChannelFn) -> ChannelFn:
        CHANNELS.append(
            Channel(
                name=name,
                label=label or name.capitalize(),
                fn=fn,
                uses=frozenset(uses),
            )
        )
        return fn

    return decorator


def channel_named(name: str) -> Channel | None:
    return next((ch for ch in CHANNELS if ch.name == name), None)


def channel_labelled(label: str) -> Channel | None:
    return next((ch for ch in CHANNELS if ch.label == label), None)
