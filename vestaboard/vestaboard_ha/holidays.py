"""What the days turned out to be: the daily cache, and the holidays it names.

Two things are kept, because they go stale at completely different rates:

* **A day**, ``days/2026-09-22.json``, is the ids Checkiday gave for that date.
  One file per date, written the first time we ask, so a second fetch on the
  same day costs nothing of the monthly allowance -- and the run of files is a
  record of what a year held.
* **A holiday**, ``events/<id>.json``, is what one id means: its name, its page,
  and whether it runs longer than a day. A holiday comes round again, so this
  is written once and rewritten only when Checkiday says something new about it.

Keeping the two apart is what makes a day cheap to write -- a date is a list of
ids, and the names sit beside it rather than in it -- and it is what makes the
names worth keeping: a year of days is a year of holidays whose names we
already have, without asking for any of them twice.

Both are plain JSON under the app's own storage, which Supervisor keeps across
restarts and updates, so the whole store can be read, edited or thrown away
with a text editor.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .checkiday import Holiday

_LOGGER = logging.getLogger(__name__)

SUFFIX = ".json"

#: The daily cache, and the durable one. Two directories rather than one, so
#: that a date and an id can never collide and either can be cleared alone.
DAYS = "days"
EVENTS = "events"

#: What an id is allowed to look like. It becomes a file name, so it has to be
#: one plain word and nothing that climbs out of the directory. Checkiday's own
#: are 32 hex characters; this is looser than that on purpose, since a source
#: that changes its mind about the shape of an id should cost us that holiday
#: rather than the store.
EVENT_ID = re.compile(r"[\w-]{1,64}")


def _read(path: Path) -> dict[str, Any] | None:
    """One file of the store, or None if it is not there or not readable.

    A file that will not parse is the same as a missing one as far as anything
    here is concerned: a day that cannot be read is a day worth fetching again,
    and a holiday that cannot be read is a name worth asking for again. It is
    still worth saying so in the log, since neither should happen.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        _LOGGER.warning("cannot read %s, treating it as missing: %s", path, exc)
        return None

    if not isinstance(payload, dict):
        _LOGGER.warning("%s holds %r rather than an object", path, payload)
        return None
    return payload


def _write(path: Path, payload: dict[str, Any]) -> None:
    """Write one file of the store, all of it or none of it.

    Through a temporary name and a rename, because a half-written file is
    worse here than no file: a day that is half a list of ids reads as a day
    we already fetched, and we would never go back for the rest of it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.writing")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


class HolidayStore:
    """The two caches, side by side in one directory."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    @property
    def days_dir(self) -> Path:
        return self.directory / DAYS

    @property
    def events_dir(self) -> Path:
        return self.directory / EVENTS

    def day_path(self, day: date) -> Path:
        """Where a date's ids are kept. The name is the date, so it sorts."""
        return self.days_dir / f"{day.isoformat()}{SUFFIX}"

    def event_path(self, event_id: str) -> Path:
        """Where one holiday is kept. The name is its id, which is the point."""
        if not EVENT_ID.fullmatch(event_id):
            raise ValueError(
                f"{event_id!r} cannot be a holiday id; an id is one plain word"
            )
        return self.events_dir / f"{event_id}{SUFFIX}"

    def ids_for(self, day: date) -> list[str] | None:
        """The ids we have for a date, or None if we never asked about it.

        None and the empty list are different answers, and the difference is
        the whole use of this cache: nothing yet means go and ask, and a day
        that genuinely held no holidays means do not ask again.
        """
        payload = _read(self.day_path(day))
        if payload is None:
            return None
        ids = payload.get("ids")
        if not isinstance(ids, list):
            _LOGGER.warning("%s has no list of ids in it", self.day_path(day))
            return None
        return [str(event_id) for event_id in ids]

    def holiday(self, event_id: str) -> Holiday | None:
        """What one id means, or None if the store has never been told."""
        try:
            path = self.event_path(event_id)
        except ValueError as exc:
            _LOGGER.warning("%s", exc)
            return None

        payload = _read(path)
        if payload is None:
            return None

        name = str(payload.get("name") or "").strip()
        if not name:
            _LOGGER.warning("%s has no name in it", path)
            return None

        return Holiday(
            id=event_id,
            name=name,
            url=str(payload.get("url") or ""),
            multiday=bool(payload.get("multiday")),
        )

    def holidays_for(self, day: date) -> list[Holiday]:
        """A date's holidays, named: the daily cache joined to the durable one.

        A date we never asked about, and one that held nothing, both come back
        empty -- a caller that needs to tell them apart wants ``ids_for``.
        """
        holidays = []
        for event_id in self.ids_for(day) or []:
            holiday = self.holiday(event_id)
            if holiday is None:
                _LOGGER.warning(
                    "%s was a holiday on %s, but the store has no name for it",
                    event_id,
                    day,
                )
                continue
            holidays.append(holiday)
        return holidays

    def days(self) -> list[date]:
        """Every date we have asked about, oldest first."""
        found = []
        for path in self.days_dir.glob(f"*{SUFFIX}"):
            try:
                found.append(date.fromisoformat(path.stem))
            except ValueError:
                _LOGGER.warning("%s is not a date, so it is not a day", path)
        return sorted(found)

    def remember(self, day: date, holidays: list[Holiday]) -> None:
        """Write a day down: each holiday in the durable cache, then the date.

        The date is written last on purpose. It is the file that says we asked,
        so until every name beside it is safely down, we have not asked.
        """
        for holiday in holidays:
            self._remember_holiday(holiday, day)

        _write(
            self.day_path(day),
            {
                "date": day.isoformat(),
                # The container's clock, which Supervisor sets to the same
                # timezone Home Assistant is in.
                "fetched": datetime.now().isoformat(timespec="seconds"),
                "ids": [holiday.id for holiday in holidays],
            },
        )
        _LOGGER.info("holidays: wrote %d for %s", len(holidays), day)

    def _remember_holiday(self, holiday: Holiday, day: date) -> None:
        """One holiday in the durable cache, kept current but not rewritten.

        ``first_seen`` is the first date we saw it on rather than the day the
        file was written, so backfilling an old date does not claim we knew
        about it sooner than we did. Everything else is Checkiday's latest word
        on the holiday, which wins -- a renamed holiday is the same holiday.
        """
        try:
            path = self.event_path(holiday.id)
        except ValueError as exc:
            _LOGGER.warning("%s; leaving it out", exc)
            return

        known = _read(path) or {}
        first_seen = str(known.get("first_seen") or "").strip() or day.isoformat()
        payload = {
            "id": holiday.id,
            "name": holiday.name,
            "url": holiday.url,
            "multiday": holiday.multiday,
            # The earlier of what we thought and what we are being told, so a
            # day fetched out of order does not push the date forwards.
            "first_seen": min(first_seen, day.isoformat()),
        }

        # A holiday that has not changed is a file not worth touching, which
        # leaves its modified time meaning something.
        if known == payload:
            return
        _write(path, payload)
