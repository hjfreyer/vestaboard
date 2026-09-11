import pytest

from vestaboard_ha import app, registry


@pytest.fixture
def clean_registry(monkeypatch):
    monkeypatch.setattr(registry, "SCHEDULED_RULES", [])
    monkeypatch.setattr(registry, "STATE_RULES", [])


def _event(entity_id="binary_sensor.door", new="on"):
    return {
        "data": {
            "entity_id": entity_id,
            "old_state": {"state": "off"},
            "new_state": {"state": new},
        }
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

    await app._dispatch_state_change(None, _event())

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

    await app._dispatch_state_change(None, _event())

    assert fired == ["survivor"]
    assert "boom" in caplog.text


def test_every_scheduled_rule_becomes_a_job(clean_registry):
    @registry.on_schedule(hour=7, minute=0)
    async def morning(ctx):
        pass

    scheduler = app._build_scheduler(ctx=None)

    assert [job.id for job in scheduler.get_jobs()] == ["morning"]


def test_shipped_rules_all_register():
    from vestaboard_ha import rules  # noqa: F401

    assert registry.SCHEDULED_RULES
    assert registry.STATE_RULES
