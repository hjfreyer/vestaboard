import json
import os
from datetime import date

import pytest

from vestaboard_ha.checkiday import Holiday
from vestaboard_ha.holidays import HolidayStore, Judgement
from vestaboard_ha.judge import Exemplar

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


def test_an_ask_that_came_to_nothing_is_counted(tmp_path):
    store = HolidayStore(tmp_path)

    assert store.attempts_for(A_DAY) == 0
    assert store.note_attempt(A_DAY) == 1
    assert store.note_attempt(A_DAY) == 2
    assert store.attempts_for(A_DAY) == 2
    # Counting the asks is not the same as having an answer.
    assert store.ids_for(A_DAY) is None


def test_counting_a_failure_does_not_lose_a_day_we_already_had(tmp_path):
    store = HolidayStore(tmp_path)
    store.remember(A_DAY, [SPINACH])

    store.note_attempt(A_DAY)

    assert store.ids_for(A_DAY) == [SPINACH.id]
    assert store.attempts_for(A_DAY) == 1


def test_a_day_that_answers_starts_counting_again(tmp_path):
    store = HolidayStore(tmp_path)
    store.note_attempt(A_DAY)
    store.note_attempt(A_DAY)

    store.remember(A_DAY, [SPINACH])

    assert store.attempts_for(A_DAY) == 0


def edit(store, holiday, **fields):
    """Change a holiday's file by hand, the way the household would."""
    path = store.event_path(holiday.id)
    payload = json.loads(path.read_text())
    payload.update(fields)
    path.write_text(json.dumps(payload))


def test_a_holiday_nobody_has_judged_has_no_verdict(tmp_path):
    store = HolidayStore(tmp_path)
    store.remember(A_DAY, [SPINACH])

    assert store.judgement(SPINACH.id) == Judgement()
    assert store.judgement(SPINACH.id).label is None
    # Nor does one the store has never heard of.
    assert store.judgement("ffffffffffffffffffffffffffffffff").label is None


def test_a_verdict_is_kept_beside_the_name(tmp_path):
    store = HolidayStore(tmp_path)
    store.remember(A_DAY, [SPINACH])

    store.judge(SPINACH.id, "show", "A silly food day")

    assert store.judgement(SPINACH.id) == Judgement("show", "A silly food day")
    assert store.holiday(SPINACH.id) == SPINACH
    payload = json.loads(store.event_path(SPINACH.id).read_text())
    assert payload["judged"]


def test_a_verdict_on_a_holiday_the_store_never_had_is_not_written(tmp_path, caplog):
    store = HolidayStore(tmp_path)

    store.judge(SPINACH.id, "show")

    assert not store.event_path(SPINACH.id).exists()
    assert "no name for it" in caplog.text


def test_a_verdict_has_to_be_one_of_the_three(tmp_path):
    store = HolidayStore(tmp_path)
    store.remember(A_DAY, [SPINACH])

    with pytest.raises(ValueError):
        store.judge(SPINACH.id, "lame")


def test_the_household_s_override_is_the_verdict_that_counts(tmp_path):
    store = HolidayStore(tmp_path)
    store.remember(A_DAY, [SPINACH])
    store.judge(SPINACH.id, "show", "A silly food day")

    edit(store, SPINACH, override=" Hide ")

    judgement = store.judgement(SPINACH.id)
    assert judgement.verdict == "show"
    assert judgement.label == "hide"


def test_an_override_that_is_not_a_verdict_is_ignored_and_logged(tmp_path, caplog):
    store = HolidayStore(tmp_path)
    store.remember(A_DAY, [SPINACH])
    store.judge(SPINACH.id, "show")

    edit(store, SPINACH, override="nope")

    assert store.judgement(SPINACH.id).label == "show"
    assert "'nope', which is not one of" in caplog.text


def test_a_holiday_checkiday_says_something_new_about_keeps_its_verdict(tmp_path):
    store = HolidayStore(tmp_path)
    store.remember(A_DAY, [CHICKEN])
    store.judge(CHICKEN.id, "show", "Chickens")
    edit(store, CHICKEN, override="hide", exemplar=True)

    renamed = CHICKEN._replace(name="National Chicken Appreciation Month")
    store.remember(ANOTHER_DAY, [renamed])

    assert store.holiday(CHICKEN.id) == renamed
    assert store.judgement(CHICKEN.id) == Judgement("show", "Chickens", "hide", True)


def test_every_holiday_the_store_knows_comes_back_in_the_order_of_its_ids(tmp_path):
    store = HolidayStore(tmp_path)
    store.remember(A_DAY, [CHICKEN])
    store.remember(ANOTHER_DAY, [SPINACH])

    assert store.known() == [SPINACH, CHICKEN]


def test_the_exemplars_are_the_holidays_marked_as_one(tmp_path):
    store = HolidayStore(tmp_path)
    store.remember(A_DAY, [SPINACH, CHICKEN])
    store.judge(SPINACH.id, "show", "A silly food day")
    store.judge(CHICKEN.id, "show", "Chickens")

    edit(store, SPINACH, exemplar=True)

    assert store.exemplars() == [
        Exemplar("Fresh Spinach Day", "show", "A silly food day")
    ]


def test_an_exemplar_teaches_its_override_without_the_reason_against_it(tmp_path):
    store = HolidayStore(tmp_path)
    store.remember(A_DAY, [SPINACH])
    store.judge(SPINACH.id, "show", "A silly food day")

    edit(store, SPINACH, exemplar=True, override="hide")

    assert store.exemplars() == [Exemplar("Fresh Spinach Day", "hide")]


def test_an_override_that_agrees_keeps_the_reason(tmp_path):
    store = HolidayStore(tmp_path)
    store.remember(A_DAY, [SPINACH])
    store.judge(SPINACH.id, "show", "A silly food day")

    edit(store, SPINACH, exemplar=True, override="show")

    assert store.exemplars() == [
        Exemplar("Fresh Spinach Day", "show", "A silly food day")
    ]


def test_an_exemplar_nobody_has_judged_has_nothing_to_teach(tmp_path, caplog):
    store = HolidayStore(tmp_path)
    store.remember(A_DAY, [SPINACH])

    edit(store, SPINACH, exemplar=True)

    assert store.exemplars() == []
    assert "no verdict or override" in caplog.text


def test_only_a_true_exemplar_is_one(tmp_path):
    store = HolidayStore(tmp_path)
    store.remember(A_DAY, [SPINACH])
    store.judge(SPINACH.id, "show")

    edit(store, SPINACH, exemplar="false")

    assert store.exemplars() == []


def test_deciding_writes_the_override_and_the_exemplar_and_nothing_else(tmp_path):
    store = HolidayStore(tmp_path)
    store.remember(A_DAY, [SPINACH])
    store.judge(SPINACH.id, "show", "A silly food day")

    store.decide(SPINACH.id, "hide", True)
    assert store.judgement(SPINACH.id) == Judgement(
        "show", "A silly food day", "hide", True
    )

    store.decide(SPINACH.id, None, False)
    payload = json.loads(store.event_path(SPINACH.id).read_text())
    assert "override" not in payload and "exemplar" not in payload
    assert store.holiday(SPINACH.id) == SPINACH


def test_deciding_about_a_holiday_that_is_not_there_is_an_error(tmp_path):
    store = HolidayStore(tmp_path)

    with pytest.raises(ValueError):
        store.decide(SPINACH.id, "show", False)
    with pytest.raises(ValueError):
        store.decide("../escape", "show", False)


def test_whether_a_holiday_goes_up():
    assert Judgement("show").goes_up(judging=True)
    assert not Judgement("hide").goes_up(judging=True)
    assert Judgement("hide", override="show").goes_up(judging=True)
    assert not Judgement("show", override="sensitive").goes_up(judging=False)
    # Unjudged: up when nothing is judging, off while waiting on Claude.
    assert Judgement().goes_up(judging=False)
    assert not Judgement().goes_up(judging=True)
