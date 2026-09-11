"""Decorators used by rules.py to declare when messages get sent."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .app import Context

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
        if self.to_state is not None:
            new = event_data.get("new_state") or {}
            if new.get("state") != self.to_state:
                return False
        if self.from_state is not None:
            old = event_data.get("old_state") or {}
            if old.get("state") != self.from_state:
                return False
        return True


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
    """Run when an entity changes state."""

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
