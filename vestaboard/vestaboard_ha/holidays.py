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

A holiday's file also keeps what Claude made of it (``judge.py``) -- its
``verdict`` and the ``reason`` for it -- and two fields that are the household's
to set by hand: ``override``, a verdict that wins over Claude's, and
``exemplar``, which makes the holiday one of the examples Claude is shown.

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
from typing import Any, NamedTuple

from .checkiday import Holiday
from .judge import SHOW, VERDICTS, Exemplar

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

#: The fields of a holiday's file that are about whether to show it rather
#: than about what it is. Checkiday knows nothing of them, so a holiday it
#: tells us something new about keeps them.
JUDGEMENT = ("verdict", "reason", "judged", "override", "exemplar")


class Judgement(NamedTuple):
    """Whether a holiday goes on the board, and who said so.

    ``verdict`` is Claude's and ``override`` is the household's; ``label`` is
    the one that counts. None for both is a holiday nobody has judged yet.
    """

    verdict: str | None = None
    reason: str = ""
    override: str | None = None
    exemplar: bool = False

    @property
    def label(self) -> str | None:
        return self.override or self.verdict

    def goes_up(self, judging: bool) -> bool:
        """Whether this holiday is one the board will show.

        ``judging`` is whether there is a judge to wait for. Without one, a
        holiday nobody has judged goes up, which is how the board behaved
        before there was one; with one, it is kept off until it is judged,
        since with a cheer in front of every name an unchecked memorial is the
        worse mistake. Either way an override counts.
        """
        if self.label is None:
            return not judging
        return self.label == SHOW


def _verdict(raw: Any, path: Path, field: str) -> str | None:
    """A verdict from a file, or None if it is missing or not one of the three.

    These are written by hand as often as not, so case and stray spaces are
    forgiven; anything else is worth a word in the log, since a typo in an
    override would otherwise quietly hand the holiday back to Claude.
    """
    if raw is None or raw == "":
        return None
    said = str(raw).strip().lower()
    if said in VERDICTS:
        return said
    _LOGGER.warning(
        "%s has %s %r, which is not one of %s; ignoring it",
        path,
        field,
        raw,
        ", ".join(VERDICTS),
    )
    return None


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


def _attempts(payload: dict[str, Any] | None) -> int:
    """How many failed asks a day's file records, and none for anything odd."""
    attempts = (payload or {}).get("attempts")
    return attempts if isinstance(attempts, int) and attempts > 0 else 0


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

    def attempts_for(self, day: date) -> int:
        """How many times we have asked about a day and come away with nothing.

        A day that answered is back to none of them: ``remember`` writes the
        day out fresh, and a day whose holidays we know is not asked again.
        """
        return _attempts(_read(self.day_path(day)))

    def note_attempt(self, day: date) -> int:
        """Write down that we asked about a day and it did not go well.

        Every ask spends one of the key's monthly allowance whether or not it
        came back with anything, and the free allowance is a hundred -- so an
        automation on a time pattern and an API having a bad morning could
        between them spend the month before lunch. Counting the failures is
        what lets a rule give up until tomorrow.

        Whatever the day already said is kept, so that a refresh that fails
        does not cost us the holidays the day already had.
        """
        payload = _read(self.day_path(day)) or {}
        payload["date"] = day.isoformat()
        payload["attempts"] = _attempts(payload) + 1
        # The clock, not the date: which day it was is in the file name, and
        # what is wanted here is when we last bothered them.
        payload["tried"] = datetime.now().isoformat(timespec="seconds")
        _write(self.day_path(day), payload)
        return payload["attempts"]

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

    def known(self) -> list[Holiday]:
        """Every holiday the store has a name for, in the order of their ids."""
        found = []
        for path in sorted(self.events_dir.glob(f"*{SUFFIX}")):
            holiday = self.holiday(path.stem)
            if holiday is not None:
                found.append(holiday)
        return found

    def judgement(self, event_id: str) -> Judgement:
        """What has been decided about a holiday: nothing, if nobody has."""
        try:
            path = self.event_path(event_id)
        except ValueError:
            return Judgement()
        payload = _read(path) or {}
        return Judgement(
            verdict=_verdict(payload.get("verdict"), path, "verdict"),
            reason=str(payload.get("reason") or "").strip(),
            override=_verdict(payload.get("override"), path, "override"),
            exemplar=payload.get("exemplar") is True,
        )

    def judge(self, event_id: str, verdict: str, reason: str = "") -> None:
        """Write down Claude's verdict on a holiday, keeping everything else.

        Only a holiday the store already has is judged: a verdict on its own,
        with no name beside it, is no use to anything.
        """
        if verdict not in VERDICTS:
            raise ValueError(f"{verdict!r} is not one of {', '.join(VERDICTS)}")
        try:
            path = self.event_path(event_id)
        except ValueError as exc:
            _LOGGER.warning("%s; leaving it unjudged", exc)
            return
        payload = _read(path)
        if payload is None:
            _LOGGER.warning("%s was judged, but the store has no name for it", event_id)
            return
        payload["verdict"] = verdict
        payload["reason"] = reason
        payload["judged"] = datetime.now().isoformat(timespec="seconds")
        _write(path, payload)

    def decide(self, event_id: str, override: str | None, exemplar: bool) -> None:
        """Write down what the household decided about a holiday.

        ``override`` is a verdict that wins over Claude's, or None to leave it
        to Claude; ``exemplar`` is whether the holiday is one of the examples.
        Everything else in the file is kept as it was.
        """
        if override is not None and override not in VERDICTS:
            raise ValueError(f"{override!r} is not one of {', '.join(VERDICTS)}")
        path = self.event_path(event_id)
        payload = _read(path)
        if payload is None:
            raise ValueError(f"there is no holiday {event_id} to decide about")
        if override is None:
            payload.pop("override", None)
        else:
            payload["override"] = override
        if exemplar:
            payload["exemplar"] = True
        else:
            payload.pop("exemplar", None)
        _write(path, payload)

    def exemplars(self) -> list[Exemplar]:
        """The household's examples: every holiday marked ``exemplar``.

        Each is shown with the verdict that counts -- the override if there is
        one -- and in the order of their ids, so the prompt they go into stays
        the same from one day to the next. To give an exemplar a reason of your
        own, edit its ``verdict`` and ``reason`` rather than overriding it:
        nothing judges an exemplar again. An exemplar nobody has judged has
        nothing to teach, and is left out with a word in the log.
        """
        found = []
        for holiday in self.known():
            judgement = self.judgement(holiday.id)
            if not judgement.exemplar:
                continue
            if judgement.label is None:
                _LOGGER.warning(
                    "%r is an exemplar with no verdict or override; leaving it out",
                    holiday.name,
                )
                continue
            # Claude's reason argues for Claude's verdict, so an override that
            # disagrees with it goes in without one rather than with the
            # argument for the other side.
            reason = judgement.reason if judgement.label == judgement.verdict else ""
            found.append(Exemplar(holiday.name, judgement.label, reason))
        return found

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
        # Whatever was decided about it is ours rather than Checkiday's, and a
        # renamed holiday is the same holiday, so it keeps its verdict.
        payload.update({key: known[key] for key in JUDGEMENT if key in known})

        # A holiday that has not changed is a file not worth touching, which
        # leaves its modified time meaning something.
        if known == payload:
            return
        _write(path, payload)
