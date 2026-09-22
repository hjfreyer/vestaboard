import json
import logging
from datetime import date

import pytest

from vestaboard_ha.checkiday import Checkiday, CheckidayError, Holiday, holidays_in

A_DAY = date(2026, 9, 22)

SPINACH = {
    "id": "676cd91e31adcacd0a505117d2c4a842",
    "name": "Fresh Spinach Day",
    "url": "https://www.checkiday.com/676cd/fresh-spinach-day",
}
FALL = {
    "id": "0a505117d2c4a842676cd91e31adcacd",
    "name": "First Day of Fall",
    "url": "https://www.checkiday.com/0a505/first-day-of-fall",
}
AWARENESS = {
    "id": "adcacd0a505117d2c4a842676cd91e31",
    "name": "National Chicken Month",
    "url": "https://www.checkiday.com/adcac/national-chicken-month",
}


def a_listing(**lists):
    return {
        "adult": False,
        "date": "9/22/2026",
        "timezone": "America/Los_Angeles",
        "events": [],
        "multiday_starting": [],
        "multiday_ongoing": [],
        **lists,
    }


class FakeResponse:
    def __init__(self, status, body, headers):
        self.status = status
        self.headers = headers
        self._body = body

    async def text(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    def __init__(self, payload=None, *, status=200, body=None, headers=None):
        self.status = status
        self.body = json.dumps(payload) if body is None else body
        self.headers = headers or {}
        self.calls = []

    def get(self, url, *, params=None, headers=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        return FakeResponse(self.status, self.body, self.headers)


@pytest.mark.asyncio
async def test_a_date_s_holidays_come_back_as_one_list():
    session = FakeSession(
        a_listing(
            events=[SPINACH, FALL],
            multiday_starting=[AWARENESS],
        )
    )

    found = await Checkiday("key", session).holidays(A_DAY)

    assert found == [
        Holiday(SPINACH["id"], "Fresh Spinach Day", SPINACH["url"], False),
        Holiday(FALL["id"], "First Day of Fall", FALL["url"], False),
        Holiday(AWARENESS["id"], "National Chicken Month", AWARENESS["url"], True),
    ]


@pytest.mark.asyncio
async def test_a_week_or_a_month_already_running_is_a_holiday_too():
    session = FakeSession(a_listing(multiday_ongoing=[AWARENESS]))

    [holiday] = await Checkiday("key", session).holidays(A_DAY)

    assert holiday.name == "National Chicken Month"
    assert holiday.multiday


@pytest.mark.asyncio
async def test_the_request_carries_the_key_the_date_and_the_timezone():
    session = FakeSession(a_listing())

    await Checkiday("secret", session, timezone="America/Los_Angeles").holidays(A_DAY)

    [call] = session.calls
    assert call["url"] == "https://api.apilayer.com/checkiday/events"
    assert call["headers"]["apikey"] == "secret"
    assert call["params"]["date"] == "2026-09-22"
    assert call["params"]["timezone"] == "America/Los_Angeles"
    # The board is in a house; Checkiday's grown-up entries stay out of it.
    assert call["params"]["adult"] == "false"


@pytest.mark.asyncio
async def test_nothing_we_cannot_answer_goes_in_the_request():
    session = FakeSession(a_listing())

    await Checkiday("secret", session).holidays()

    [call] = session.calls
    assert "timezone" not in call["params"]
    assert "date" not in call["params"]


@pytest.mark.asyncio
async def test_the_same_holiday_in_two_lists_is_one_holiday():
    session = FakeSession(
        a_listing(multiday_starting=[AWARENESS], multiday_ongoing=[AWARENESS])
    )

    assert len(await Checkiday("key", session).holidays(A_DAY)) == 1


@pytest.mark.asyncio
async def test_a_holiday_with_no_id_or_no_name_is_left_out():
    session = FakeSession(
        a_listing(events=[SPINACH, {"name": "Nameless"}, {"id": "x"}, "not a holiday"])
    )

    found = await Checkiday("key", session).holidays(A_DAY)

    assert [holiday.name for holiday in found] == ["Fresh Spinach Day"]


@pytest.mark.asyncio
async def test_an_error_says_what_checkiday_said():
    session = FakeSession({"error": "You have exceeded your quota"}, status=429)

    with pytest.raises(CheckidayError, match="exceeded your quota"):
        await Checkiday("key", session).holidays(A_DAY)


@pytest.mark.asyncio
async def test_a_body_that_is_not_json_is_an_error():
    session = FakeSession(body="<html>gateway timeout</html>", status=504)

    with pytest.raises(CheckidayError, match="not JSON"):
        await Checkiday("key", session).holidays(A_DAY)


@pytest.mark.asyncio
async def test_no_key_means_no_request_at_all():
    session = FakeSession(a_listing())
    checkiday = Checkiday("", session)

    assert not checkiday.configured
    with pytest.raises(CheckidayError, match="no Checkiday API key"):
        await checkiday.holidays(A_DAY)
    assert session.calls == []


@pytest.mark.asyncio
async def test_what_is_left_of_the_month_is_logged(caplog):
    caplog.set_level(logging.INFO)
    session = FakeSession(a_listing(), headers={"X-RateLimit-Remaining-Month": "97"})

    await Checkiday("key", session).holidays(A_DAY)

    assert "97 requests left this month" in caplog.text


def test_a_listing_with_no_lists_in_it_is_an_error():
    with pytest.raises(CheckidayError, match="list of holidays"):
        holidays_in({"message": "who are you?"})

    with pytest.raises(CheckidayError, match="not a listing"):
        holidays_in(["nope"])

    with pytest.raises(CheckidayError, match="not a list of holidays"):
        holidays_in({"events": "Fresh Spinach Day"})


def test_a_day_with_nothing_on_it_is_no_holidays_rather_than_an_error():
    assert holidays_in(a_listing()) == []
