import pytest

from vestaboard_ha import app, registry


@pytest.fixture
def clean_registry(monkeypatch):
    monkeypatch.setattr(registry, "SCHEDULED_RULES", [])
    monkeypatch.setattr(registry, "STATE_RULES", [])
    monkeypatch.setattr(registry, "ACTION_RULES", [])


def _event(entity_id="binary_sensor.door", new="on"):
    return {
        "event_type": app.STATE_CHANGED,
        "data": {
            "entity_id": entity_id,
            "old_state": {"state": "off"},
            "new_state": {"state": new},
        },
    }


@pytest.mark.asyncio
async def test_dispatch_runs_only_matching_rules(clean_registry):
    fired = []

    @registry.on_state("binary_sensor.door", to="on")
    async def door(ctx, event):
        fired.append("door")

    @registry.on_state("binary_sensor.window", to="on")
    async def window(ctx, event):
        fired.append("window")

    await app._dispatch(None, _event())

    assert fired == ["door"]


@pytest.mark.asyncio
async def test_one_failing_rule_does_not_stop_the_others(clean_registry, caplog):
    fired = []

    @registry.on_state("binary_sensor.door")
    async def boom(ctx, event):
        raise RuntimeError("kaboom")

    @registry.on_state("binary_sensor.door")
    async def survivor(ctx, event):
        fired.append("survivor")

    await app._dispatch(None, _event())

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
        None, {"event_type": "vestaboard_show_art", "data": {"name": "heart"}}
    )

    assert got == [{"name": "heart"}]


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
    @registry.on_state("binary_sensor.door")
    async def door(ctx, event):
        pass

    @registry.on_action("show_art")
    async def show_art(ctx, data):
        pass

    @registry.on_action("show_art")
    async def also_show_art(ctx, data):
        pass

    assert app._event_types() == [app.STATE_CHANGED, "vestaboard_show_art"]


def test_every_scheduled_rule_becomes_a_job(clean_registry):
    @registry.on_schedule(hour=7, minute=0)
    async def morning(ctx):
        pass

    scheduler = app._build_scheduler(ctx=None)

    assert [job.id for job in scheduler.get_jobs()] == ["morning"]


def test_shipped_rules_all_register():
    from vestaboard_ha import rules  # noqa: F401

    assert registry.STATE_RULES
    assert [rule.event_type for rule in registry.ACTION_RULES] == [
        "vestaboard_show_art"
    ]
