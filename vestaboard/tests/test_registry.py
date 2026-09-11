from vestaboard_ha.registry import StateRule


def _rule(**kwargs):
    return StateRule(name="r", fn=None, entity_id="binary_sensor.door", **kwargs)


def _event(entity_id="binary_sensor.door", old="off", new="on"):
    return {
        "entity_id": entity_id,
        "old_state": {"state": old},
        "new_state": {"state": new},
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
