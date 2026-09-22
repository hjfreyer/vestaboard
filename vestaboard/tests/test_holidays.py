import json
import os
from datetime import date

import pytest

from vestaboard_ha.checkiday import Holiday
from vestaboard_ha.holidays import HolidayStore

A_DAY = date(2026, 9, 22)
ANOTHER_DAY = date(2026, 9, 23)

SPINACH = Holiday("676cd91e31adcacd0a505117d2c4a842", "Fresh Spinach Day", "u1", False)
CHICKEN = Holiday(
    "adcacd0a505117d2c4a842676cd91e31", "National Chicken Month", "u2", True
)


def test_a_day_we_never_asked_about_is_not_a_day_with_nothing_on_it(tmp_path):
    store = HolidayStore(tmp_path)

    assert store.ids_for(A_DAY) is None

    store.remember(A_DAY, [])

    assert store.ids_for(A_DAY) == []
    assert store.holidays_for(A_DAY) == []


def test_a_day_and_its_holidays_come_back_as_they_went_in(tmp_path):
    store = HolidayStore(tmp_path)

    store.remember(A_DAY, [SPINACH, CHICKEN])

    assert store.ids_for(A_DAY) == [SPINACH.id, CHICKEN.id]
    assert store.holidays_for(A_DAY) == [SPINACH, CHICKEN]
    assert store.holiday(CHICKEN.id) == CHICKEN


def test_the_two_caches_are_a_file_per_day_and_a_file_per_holiday(tmp_path):
    store = HolidayStore(tmp_path)

    store.remember(A_DAY, [SPINACH])

    day = tmp_path / "days" / "2026-09-22.json"
    holiday = tmp_path / "events" / f"{SPINACH.id}.json"
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*.json")) == sorted(
        [day.relative_to(tmp_path), holiday.relative_to(tmp_path)]
    )
    assert json.loads(day.read_text())["ids"] == [SPINACH.id]
    assert json.loads(holiday.read_text())["name"] == "Fresh Spinach Day"


def test_a_holiday_is_written_once_and_named_on_every_day_it_falls(tmp_path):
    store = HolidayStore(tmp_path)
    store.remember(A_DAY, [CHICKEN])

    # A file nothing has changed is a file nothing should have touched.
    path = store.event_path(CHICKEN.id)
    os.utime(path, (0, 0))
    store.remember(ANOTHER_DAY, [CHICKEN])

    assert path.stat().st_mtime == 0
    assert store.holidays_for(ANOTHER_DAY) == [CHICKEN]


def test_a_renamed_holiday_is_the_same_holiday_under_its_new_name(tmp_path):
    store = HolidayStore(tmp_path)
    store.remember(A_DAY, [CHICKEN])

    renamed = CHICKEN._replace(name="National Chicken Appreciation Month")
    store.remember(ANOTHER_DAY, [renamed])

    assert store.holiday(CHICKEN.id) == renamed
    # It is still a holiday we have known about since the day we first saw it.
    assert json.loads(store.event_path(CHICKEN.id).read_text())["first_seen"] == (
        A_DAY.isoformat()
    )


def test_a_day_filled_in_afterwards_does_not_push_first_seen_forwards(tmp_path):
    store = HolidayStore(tmp_path)
    store.remember(ANOTHER_DAY, [SPINACH])

    store.remember(A_DAY, [SPINACH])

    first_seen = json.loads(store.event_path(SPINACH.id).read_text())["first_seen"]
    assert first_seen == A_DAY.isoformat()


def test_an_id_that_is_not_a_word_is_not_a_file_name(tmp_path):
    store = HolidayStore(tmp_path)

    with pytest.raises(ValueError, match="one plain word"):
        store.event_path("../../etc/passwd")

    # It costs us that holiday and not the day it fell on.
    store.remember(A_DAY, [Holiday("../escape", "Nowhere Day"), SPINACH])
    assert store.holidays_for(A_DAY) == [SPINACH]
    assert store.holiday("../escape") is None


def test_a_file_that_will_not_parse_is_a_file_worth_fetching_again(tmp_path):
    store = HolidayStore(tmp_path)
    store.remember(A_DAY, [SPINACH])

    store.day_path(A_DAY).write_text("{ this is not json")

    assert store.ids_for(A_DAY) is None


def test_a_holiday_we_have_no_name_for_is_left_out_of_the_day(tmp_path, caplog):
    store = HolidayStore(tmp_path)
    store.remember(A_DAY, [SPINACH, CHICKEN])
    store.event_path(CHICKEN.id).unlink()

    assert store.holidays_for(A_DAY) == [SPINACH]
    assert "no name for it" in caplog.text


def test_every_day_we_have_asked_about_comes_back_in_order(tmp_path):
    store = HolidayStore(tmp_path)
    store.remember(ANOTHER_DAY, [])
    store.remember(A_DAY, [])
    (tmp_path / "days" / "notes.json").write_text("{}")

    assert store.days() == [A_DAY, ANOTHER_DAY]


def test_nothing_is_left_half_written(tmp_path):
    store = HolidayStore(tmp_path)

    store.remember(A_DAY, [SPINACH])

    assert list(tmp_path.rglob("*.writing")) == []
