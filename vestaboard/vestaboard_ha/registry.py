"""Decorators used by rules.py to declare when messages get sent."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .app import Context

#: States that mean Home Assistant has no value for the entity right now.
NO_VALUE = frozenset({"unknown", "unavailable"})

ScheduledFn = Callable[["Context"], Awaitable[None]]
StateFn = Callable[["Context", dict[str, Any]], Awaitable[None]]
ActionFn = Callable[["Context", dict[str, Any]], Awaitable[None]]

#: Actions are Home Assistant events under our own name, so that an automation
#: firing ``vestaboard_show_art`` cannot collide with anything else.
ACTION_PREFIX = "vestaboard_"


def action_event_type(action: str) -> str:
    """Event type Home Assistant fires to run the named action."""
    return f"{ACTION_PREFIX}{action}"


@dataclass(frozen=True)
class ScheduledRule:
    name: str
    fn: ScheduledFn
    cron: dict[str, Any]


@dataclass(frozen=True)
class ActionRule:
    name: str
    fn: ActionFn
    action: str

    @property
    def event_type(self) -> str:
        return action_event_type(self.action)


@dataclass(frozen=True)
class StateRule:
    name: str
    fn: StateFn
    entity_id: str
    to_state: str | None = None
    from_state: str | None = None

    def matches(self, event_data: dict[str, Any]) -> bool:
        if event_data.get("entity_id") != self.entity_id:
            return False

        old = (event_data.get("old_state") or {}).get("state")
        new = (event_data.get("new_state") or {}).get("state")

        if self.to_state is not None and new != self.to_state:
            return False
        if self.from_state is not None and old != self.from_state:
            return False

        # Home Assistant fires state_changed more often than the value really
        # changes: for attribute-only edits, and once per entity on restart,
        # where the old value is simply being restored. A rule that names the
        # state it wants has already had its say above; otherwise, only a move
        # between two known values counts.
        if new == old:
            return False
        if self.from_state is None and not _has_value(old):
            return False
        if self.to_state is None and not _has_value(new):
            return False
        return True


def _has_value(state: str | None) -> bool:
    return state is not None and state not in NO_VALUE


SCHEDULED_RULES: list[ScheduledRule] = []
STATE_RULES: list[StateRule] = []
ACTION_RULES: list[ActionRule] = []


def on_schedule(**cron: Any) -> Callable[[ScheduledFn], ScheduledFn]:
    """Run on an APScheduler cron schedule, e.g. ``@on_schedule(hour=7, minute=0)``."""

    def decorator(fn: ScheduledFn) -> ScheduledFn:
        SCHEDULED_RULES.append(ScheduledRule(name=fn.__name__, fn=fn, cron=cron))
        return fn

    return decorator


def on_state(
    entity_id: str, *, to: str | None = None, from_: str | None = None
) -> Callable[[StateFn], StateFn]:
    """Run when an entity takes a new value.

    Only a real change counts. Attribute-only updates, the restore that
    follows a Home Assistant restart, and values going ``unknown`` or
    ``unavailable`` all pass by without waking the rule -- unless ``to`` or
    ``from_`` names such a state, in which case you get exactly what you asked
    for.
    """

    def decorator(fn: StateFn) -> StateFn:
        STATE_RULES.append(
            StateRule(
                name=fn.__name__,
                fn=fn,
                entity_id=entity_id,
                to_state=to,
                from_state=from_,
            )
        )
        return fn

    return decorator


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
    """

    def decorator(fn: ActionFn) -> ActionFn:
        ACTION_RULES.append(ActionRule(name=fn.__name__, fn=fn, action=action))
        return fn

    return decorator
