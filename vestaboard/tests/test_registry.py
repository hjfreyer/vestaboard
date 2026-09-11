from vestaboard_ha.registry import StateRule


def _rule(**kwargs):
    return StateRule(name="r", fn=None, entity_id="binary_sensor.door", **kwargs)


def _event(entity_id="binary_sensor.door", old="off", new="on"):
    return {
        "entity_id": entity_id,
        "old_state": None if old is None else {"state": old},
        "new_state": None if new is None else {"state": new},
    }


def test_matches_on_entity_only():
    assert _rule().matches(_event())
    assert not _rule().matches(_event(entity_id="binary_sensor.other"))


def test_matches_to_state():
    assert _rule(to_state="on").matches(_event(new="on"))
    assert not _rule(to_state="on").matches(_event(new="off"))


def test_matches_from_state():
    assert _rule(from_state="off").matches(_event(old="off"))
    assert not _rule(from_state="off").matches(_event(old="unavailable"))


def test_tolerates_missing_states():
    assert not _rule(to_state="on").matches({"entity_id": "binary_sensor.door"})


def test_an_unchanged_value_is_not_a_change():
    # Home Assistant fires state_changed for attribute-only edits.
    assert not _rule().matches(_event(old="on", new="on"))
    assert not _rule(to_state="on").matches(_event(old="on", new="on"))


def test_the_restore_after_a_restart_is_not_a_change():
    assert not _rule().matches(_event(old=None, new="on"))
    assert not _rule(to_state="on").matches(_event(old=None, new="on"))


def test_losing_or_regaining_a_value_is_not_a_change():
    assert not _rule().matches(_event(old="on", new="unavailable"))
    assert not _rule().matches(_event(old="on", new="unknown"))
    assert not _rule().matches(_event(old="unavailable", new="on"))
    assert not _rule().matches(_event(old="on", new=None))


def test_asking_for_those_states_by_name_still_works():
    assert _rule(to_state="unavailable").matches(_event(old="on", new="unavailable"))
    assert _rule(from_state="unavailable").matches(_event(old="unavailable", new="on"))
