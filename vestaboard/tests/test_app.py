import pytest

from vestaboard_ha import app, registry


@pytest.fixture
def clean_registry(monkeypatch):
    monkeypatch.setattr(registry, "ACTION_RULES", [])


@pytest.mark.asyncio
async def test_one_failing_rule_does_not_stop_the_others(clean_registry, caplog):
    fired = []

    @registry.on_action("show_art")
    async def boom(ctx, data):
        raise RuntimeError("kaboom")

    @registry.on_action("show_art")
    async def survivor(ctx, data):
        fired.append("survivor")

    await app._dispatch(None, {"event_type": "vestaboard_show_art", "data": {}})

    assert fired == ["survivor"]
    assert "boom" in caplog.text


@pytest.mark.asyncio
async def test_an_action_runs_on_its_own_event(clean_registry):
    got = []

    @registry.on_action("show_art")
    async def show_art(ctx, data):
        got.append(data)

    @registry.on_action("something_else")
    async def other(ctx, data):
        got.append("other")

    await app._dispatch(
        None, {"event_type": "vestaboard_show_art", "data": {"name": "rainbow"}}
    )

    assert got == [{"name": "rainbow"}]


@pytest.mark.asyncio
async def test_an_action_with_no_data_still_runs(clean_registry):
    got = []

    @registry.on_action("show_art")
    async def show_art(ctx, data):
        got.append(data)

    await app._dispatch(None, {"event_type": "vestaboard_show_art"})

    assert got == [{}]


@pytest.mark.asyncio
async def test_a_failing_action_is_logged_not_raised(clean_registry, caplog):
    @registry.on_action("show_art")
    async def boom(ctx, data):
        raise RuntimeError("kaboom")

    await app._dispatch(None, {"event_type": "vestaboard_show_art", "data": {}})

    assert "boom" in caplog.text


def test_subscriptions_cover_every_rule_once(clean_registry):
    @registry.on_action("eggs")
    async def eggs(ctx, data):
        pass

    @registry.on_action("show_art")
    async def show_art(ctx, data):
        pass

    @registry.on_action("show_art")
    async def also_show_art(ctx, data):
        pass

    assert app._event_types() == ["vestaboard_eggs", "vestaboard_show_art"]


@pytest.mark.asyncio
async def test_an_event_no_rule_asked_for_is_ignored(clean_registry):
    @registry.on_action("show_art")
    async def show_art(ctx, data):
        raise AssertionError("a rule ran for somebody else's event")

    # We never subscribe to this one, so it should not arrive; the dispatcher
    # hands out every event it is given, though, and should find no rule here.
    await app._dispatch(None, {"event_type": "state_changed", "data": {}})


def test_shipped_rules_all_register():
    from vestaboard_ha import rules  # noqa: F401

    assert [rule.event_type for rule in registry.ACTION_RULES] == [
        "vestaboard_show_art",
        "vestaboard_eggs",
    ]
