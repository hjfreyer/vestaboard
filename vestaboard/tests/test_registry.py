from vestaboard_ha import registry


def test_an_action_is_an_event_under_our_own_name():
    # Our own prefix, so an automation firing one cannot collide with anything
    # else on the Home Assistant event bus.
    assert registry.action_event_type("show_art") == "vestaboard_show_art"


def test_a_rule_knows_the_event_that_runs_it():
    rule = registry.ActionRule(name="eggs", fn=None, action="eggs")

    assert rule.event_type == "vestaboard_eggs"
