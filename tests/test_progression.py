"""The progression rules, tested as an input -> expected output table."""
import pytest

from app.progression import next_miss_count, plan_after_gap, progression, target_was_hit


@pytest.mark.parametrize(
    "size, weight, hit, rpe, misses, action, new_weight",
    [
        # Target hit, RPE < 10 -> increase by lift size
        ("big", 100, True, 8, 0, "increase", 105),
        ("small", 40, True, 9, 0, "increase", 42.5),
        # Target hit at RPE 10 -> repeat (with +2.5 option, checked below)
        ("big", 100, True, 10, 0, "repeat", 100),
        # RPE not logged -> be cautious, treat like RPE 10
        ("big", 100, True, None, 0, "repeat", 100),
        # Missed, first time -> repeat
        ("big", 100, False, 9, 0, "repeat", 100),
        # Missed again -> drop
        ("big", 100, False, 9, 1, "drop", 95),
        ("small", 40, False, 10, 2, "drop", 37.5),
        # A hit after misses still increases (counter resets separately)
        ("big", 100, True, 7, 3, "increase", 105),
    ],
)
def test_progression_table(size, weight, hit, rpe, misses, action, new_weight):
    rec = progression(size, weight, hit, rpe, misses)
    assert rec.action == action
    assert rec.new_weight == new_weight


def test_rpe10_offers_small_increase():
    rec = progression("big", 100, True, 10, 0)
    assert rec.alternatives == [("increase", 102.5)]


def test_drop_never_goes_negative():
    assert progression("big", 2.5, False, 8, 1).new_weight == 0


def test_unknown_size_rejected():
    with pytest.raises(ValueError):
        progression("medium", 100, True, 8, 0)


def test_miss_counter():
    assert next_miss_count(progression("big", 100, False, 8, 0), 0) == 1
    assert next_miss_count(progression("big", 100, False, 8, 1), 1) == 2
    assert next_miss_count(progression("big", 100, True, 8, 2), 2) == 0
    assert next_miss_count(progression("big", 100, True, 10, 2), 2) == 0


def test_target_was_hit():
    plan = dict(target_sets=3, target_reps=5, target_weight=100)
    assert target_was_hit(**plan, logged_sets=[(100, 5), (100, 5), (100, 6)])
    assert not target_was_hit(**plan, logged_sets=[(100, 5), (100, 5), (100, 4)])
    assert not target_was_hit(**plan, logged_sets=[(100, 5), (100, 5)])
    assert target_was_hit(**plan, logged_sets=[(102.5, 5), (100, 5), (100, 5), (60, 10)])


@pytest.mark.parametrize("missed, plan", [(0, "continue"), (1, "extend"), (2, "step_back"), (4, "step_back")])
def test_plan_after_gap(missed, plan):
    assert plan_after_gap(missed) == plan
