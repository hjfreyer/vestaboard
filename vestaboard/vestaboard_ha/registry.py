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


@dataclass(frozen=True)
class ScheduledRule:
    name: str
    fn: ScheduledFn
    cron: dict[str, Any]


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
