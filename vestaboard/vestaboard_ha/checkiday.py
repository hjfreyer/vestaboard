"""Checkiday's API: which holidays a date turns out to hold.

Checkiday keeps several thousand holidays -- the national days, the awareness
months, and the properly obscure ones -- and its API hands over the ones that
fall on a given date. Each comes back as an id, a name and a URL, and it is the
id that is worth keeping: a name can be rewritten, and an id cannot.

Every call is one request of a monthly allowance, which is why nothing here
asks twice for the same day. ``holidays.py`` is what remembers a day, and the
``fetch_holidays`` rule is what decides whether to ask at all.

Two of the three things a request can say are sold rather than given, and a
plan that does not include one is not allowed to say it at all:

* ``adult``, whether to include the entries Checkiday marks unsafe for children
  or for work, is on every plan, the free one included.
* ``date``, which day to ask about, wants a Pro plan. Without one there is only
  today, which is why this is asked with no date at all and the day comes back
  in the answer.
* ``timezone``, whose today that is, wants an Enterprise plan. Without one it
  is Checkiday's own default, ``America/Chicago`` -- so the day in the answer
  is worth reading rather than assuming, since it is not necessarily the day it
  is here.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any, NamedTuple

_LOGGER = logging.getLogger(__name__)

#: Where the API lives. The path under it is the operation: ``events`` for a
#: date's holidays, ``event`` for one holiday's detail, ``search`` to find one
#: by name. Only the first of those is wanted here.
ENDPOINT = "https://api.apilayer.com/checkiday/"
EVENTS_URL = f"{ENDPOINT}events"

#: The header the key goes in. Not a bearer token and not a query parameter,
#: so it does not end up in anybody's logs.
KEY_HEADER = "apikey"

#: What is left of the month's requests, which the API says in a header rather
#: than in the body. Worth logging: the allowance is the reason for the caches.
REMAINING_HEADER = "X-RateLimit-Remaining-Month"

#: The three lists a date's holidays arrive in, and whether a holiday in each
#: runs longer than the one day. ``events`` is the single days; the other two
#: are the weeks and the months, split by whether this is the day they begin.
#: That split is about the date rather than about the holiday, so it is not
#: kept -- what a holiday is, is whether it runs long.
EVENT_LISTS: tuple[tuple[str, bool], ...] = (
    ("events", False),
    ("multiday_starting", True),
    ("multiday_ongoing", True),
)


class CheckidayError(RuntimeError):
    """Checkiday refused a request, or sent back something unreadable."""


class Holiday(NamedTuple):
    """One holiday, as a date's listing gives it.

    ``url`` is the page a person would read about it on, and ``multiday`` is
    whether it is one of the weeks and months rather than a single day.
    """

    id: str
    name: str
    url: str = ""
    multiday: bool = False


class Listing(NamedTuple):
    """A date's holidays, and the date Checkiday says they are for.

    The date is worth carrying rather than assuming: without an Enterprise plan
    the day is worked out in Checkiday's timezone and not in ours, so the two
    part company for the hours of the evening they disagree about. ``day`` is
    None when the answer did not say, which leaves the caller its own guess.
    """

    day: date | None
    holidays: list[Holiday]


#: How Checkiday writes the date it answered about: the American way round.
#: The clients type it loosely enough to be a number as well, so anything
#: unreadable is treated as no answer rather than as a wrong one.
DATE_SHAPES = ("%m/%d/%Y", "%Y-%m-%d")


def listing_date(raw: Any) -> date | None:
    """Which day a listing says it is for, if it can be read."""
    said = str(raw or "").strip()
    if not said:
        return None
    for shape in DATE_SHAPES:
        try:
            return datetime.strptime(said, shape).date()
        except ValueError:
            continue
    _LOGGER.warning("checkiday: %r is not a date I can read", raw)
    return None


def _holiday(entry: Any, multiday: bool) -> Holiday | None:
    """One entry of a listing, or None if it is not a holiday we can use.

    An entry without an id or a name is no use to us -- the id is what the
    store files it under, and the name is the whole point -- but it is also no
    reason to lose the rest of the day, so it is dropped with a word in the log.
    """
    if not isinstance(entry, Mapping):
        _LOGGER.warning("checkiday: %r is not a holiday; leaving it out", entry)
        return None

    event_id = str(entry.get("id") or "").strip()
    name = str(entry.get("name") or "").strip()
    if not event_id or not name:
        _LOGGER.warning(
            "checkiday: %r has no id or no name; leaving it out", entry
        )
        return None

    return Holiday(
        id=event_id,
        name=name,
        url=str(entry.get("url") or "").strip(),
        multiday=multiday,
    )


def holidays_in(payload: Any) -> Listing:
    """Every holiday in a listing: the single days first, the longer ones after.

    A listing with none of the three lists in it is not a listing at all --
    an error page, or an API that has moved on -- and that is worth saying
    rather than reporting a quiet day with no holidays in it.
    """
    if not isinstance(payload, Mapping):
        raise CheckidayError(f"{payload!r} is not a listing of holidays")

    wanted = [key for key, _ in EVENT_LISTS]
    if not any(key in payload for key in wanted):
        raise CheckidayError(
            f"nothing in {sorted(payload)} is a list of holidays; "
            f"expected {', '.join(wanted)}"
        )

    # By id, so that a holiday listed twice is one holiday. Insertion order is
    # kept, which is the order the API put them in, single days first.
    found: dict[str, Holiday] = {}
    for key, multiday in EVENT_LISTS:
        entries = payload.get(key) or []
        if not isinstance(entries, list):
            raise CheckidayError(f"{key!r} is {entries!r}, not a list of holidays")
        for entry in entries:
            holiday = _holiday(entry, multiday)
            if holiday is not None:
                found.setdefault(holiday.id, holiday)

    return Listing(listing_date(payload.get("date")), list(found.values()))


class Checkiday:
    """Reads a date's holidays. One request per call, so call it once a day."""

    def __init__(self, api_key: str, session: Any, *, timezone: str = "") -> None:
        """``timezone`` is only sent when given, and wants an Enterprise plan."""
        self._api_key = api_key
        self._session = session
        self._timezone = timezone

    @property
    def configured(self) -> bool:
        """Whether there is a key to ask with. Without one there is no asking."""
        return bool(self._api_key)

    async def holidays(
        self, day: date | None = None, *, adult: bool = False
    ) -> Listing:
        """The holidays on a date, or on Checkiday's own today without one.

        A ``day`` wants a Pro plan, so the rule asks for none and takes whatever
        today turns out to be; the answer says which day that was. ``adult`` is
        Checkiday's own switch for the entries it marks unsafe for children or
        for work, and is on every plan; this board is in a house, so it is off.
        """
        if not self._api_key:
            raise CheckidayError("no Checkiday API key configured")

        # Only what the plan allows: anything else is not ignored but refused,
        # so a free key that said either of the other two would get nothing at
        # all rather than an answer worked out some other way.
        params = {"adult": "true" if adult else "false"}
        if day is not None:
            params["date"] = day.isoformat()
        if self._timezone:
            params["timezone"] = self._timezone

        async with self._session.get(
            EVENTS_URL,
            params=params,
            headers={KEY_HEADER: self._api_key, "User-Agent": "vestaboard-ha"},
        ) as response:
            status = response.status
            body = await response.text()
            remaining = response.headers.get(REMAINING_HEADER)

        try:
            payload = json.loads(body)
        except ValueError as exc:
            raise CheckidayError(
                f"HTTP {status} from Checkiday, and {body[:200]!r} is not JSON"
            ) from exc

        if status >= 400:
            # Checkiday puts its complaint under ``error``, and the gateway in
            # front of it says ``message`` instead -- which is what a missing
            # or a wrong key comes back as, so it is the one most likely to be
            # read. Without either, the status is all there is to go on.
            said = ""
            if isinstance(payload, Mapping):
                said = payload.get("error") or payload.get("message") or ""
            raise CheckidayError(f"HTTP {status} from Checkiday: {said or body[:200]}")

        if remaining is not None:
            _LOGGER.info("checkiday: %s requests left this month", remaining)

        return holidays_in(payload)
