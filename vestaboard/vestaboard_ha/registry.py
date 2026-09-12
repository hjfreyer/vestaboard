"""The decorator used by rules.py to declare when messages get sent."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .app import Context

ActionFn = Callable[["Context", dict[str, Any]], Awaitable[None]]

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

    An add-on cannot register a real service, so an action is a custom event:
    ``@on_action("show_art")`` runs whenever something in Home Assistant fires
    ``vestaboard_show_art``. In an automation that is the **Fire event** action:

        actions:
          - event: vestaboard_show_art
            event_data:
              name: rainbow

    The rule is handed the event data, so ``event_data`` is how an automation
    passes arguments; it is ``{}`` when the automation sends none.

    This is the only way a rule runs. Home Assistant already knows how to
    trigger on a clock, on an entity changing, on the sun going down; a rule
    that ran itself would only be a second place to look, and a push to change
    what an automation changes in the editor.
    """

    def decorator(fn: ActionFn) -> ActionFn:
        ACTION_RULES.append(ActionRule(name=fn.__name__, fn=fn, action=action))
        return fn

    return decorator
