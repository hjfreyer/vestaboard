import pytest

from vestaboard_ha.rotation import REMEMBERED, Rotation


def draws(rotation, options, times, key=""):
    """What the rotation hands out over a run of picks."""
    return [rotation.choose(options, key) for _ in range(times)]


def held_back(count):
    """How many of the last picks a set of ``count`` things holds back."""
    return count // 2


def test_a_pair_never_comes_up_twice_running():
    rotation = Rotation()

    seen = draws(rotation, ["one", "two"], 20)

    assert all(a != b for a, b in zip(seen[:-1], seen[1:], strict=True))


def test_nothing_comes_back_until_half_the_others_have_been():
    options = ["one", "two", "three", "four", "five", "six"]
    rotation = Rotation()

    seen = draws(rotation, options, 60)

    window = held_back(len(options))
    for index, name in enumerate(seen[1:], start=1):
        assert name not in seen[max(0, index - window) : index]


def test_the_ones_not_held_back_are_all_still_in_the_running():
    options = ["one", "two", "three", "four", "five", "six"]
    rotation = Rotation()

    # Held back or not, every piece has its turn, and which one comes when is
    # not a fixed order the board would start to look like it was reciting.
    assert set(draws(rotation, options, 60)) == set(options)


def test_a_lone_option_is_always_the_pick():
    rotation = Rotation()

    assert draws(rotation, ["only"], 5) == ["only"] * 5


def test_each_key_is_a_rotation_of_its_own():
    rotation = Rotation()

    rotation.choose(["one", "two"], "art")
    elsewhere = draws(rotation, ["three", "four"], 4, "bedtime")

    # The bedtime picks did not use up the art rotation's memory, and a pick
    # made under one key holds nothing back under another.
    assert set(elsewhere) == {"three", "four"}
    assert set(draws(rotation, ["one", "two"], 4, "art")) == {"one", "two"}


def test_a_pick_made_elsewhere_counts_as_one_that_was_shown():
    rotation = Rotation()

    rotation.remember("one")

    assert draws(rotation, ["one", "two"], 1) == ["two"]


def test_a_set_that_shrinks_still_has_something_to_show():
    rotation = Rotation()
    draws(rotation, ["one", "two", "three", "four", "five", "six"], 10)

    # Five of the six are remembered, so a category that is down to two pieces
    # holds one back rather than finding everything it has was lately up.
    assert set(draws(rotation, ["one", "two"], 6)) == {"one", "two"}


def test_choosing_among_nothing_is_an_error():
    with pytest.raises(ValueError, match="nothing to choose from"):
        Rotation().choose([])


def test_the_memory_of_a_rotation_does_not_grow_for_ever():
    rotation = Rotation()

    draws(rotation, ["one", "two"], REMEMBERED * 3)

    # Only the last N // 2 are ever consulted; the rest are dropped rather
    # than kept for the lifetime of the app.
    assert len(rotation._recent[""]) == REMEMBERED
