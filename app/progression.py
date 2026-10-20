"""Progression rules: what to do with each exercise when a block ends.

Everything in this file is a pure function: no database, no Flask.
That keeps the rules easy to read and easy to test (see tests/test_progression.py).

Danial's rules (per exercise, judged on the final week of a 6-week block):
  1. Target hit and RPE < 10  -> increase: +5kg big lifts, +2.5kg small lifts
  2. Target hit but RPE == 10 -> repeat the block (option: +2.5kg)
  3. Target missed, 1st time  -> repeat the block
     Target missed again      -> drop the weight

The app only *suggests*. The user always makes the final call.
"""
from dataclasses import dataclass, field

# --- Settings you may want to tune -------------------------------------------

INCREMENT_KG = {"big": 5.0, "small": 2.5}

# Optional bump offered when the target was hit at RPE 10.
RPE10_OPTION_KG = 2.5

# ASSUMPTION: drop by the same amount as the normal increment.
# Change this once you decide what "drop weight" should mean.
DROP_KG = INCREMENT_KG

# Missed-week handling (see plan_after_gap).
SHORT_GAP_MAX_WEEKS = 1  # gaps up to this long: extend the block


# --- Data types ----------------------------------------------------------------

@dataclass
class Recommendation:
    action: str  # "increase" | "repeat" | "drop"
    new_weight: float
    reason: str
    missed: bool = False  # True when the target wasn't hit
    alternatives: list = field(default_factory=list)  # [(action, weight), ...]

    def to_dict(self):
        return {
            "action": self.action,
            "new_weight": self.new_weight,
            "reason": self.reason,
            "missed": self.missed,
            "alternatives": [{"action": a, "new_weight": w} for a, w in self.alternatives],
        }


# --- Rules ---------------------------------------------------------------------

def progression(size, weight, target_hit, rpe, consecutive_misses):
    """Recommend next block's working weight for ONE exercise.

    size:               "big" or "small"
    weight:             this block's final-week target weight (kg)
    target_hit:         did you complete the final-week target?
    rpe:                hardest RPE logged in the final week (None if not logged)
    consecutive_misses: misses for this exercise BEFORE this block
    """
    if size not in INCREMENT_KG:
        raise ValueError(f"unknown size {size!r}, expected 'big' or 'small'")

    # 1. The target decides first. RPE only matters if you hit it.
    if not target_hit:
        if consecutive_misses == 0:
            return Recommendation(
                "repeat", weight, "Missed target (first time): repeat the block.", missed=True
            )
        new_weight = max(0.0, weight - DROP_KG[size])
        return Recommendation(
            "drop", new_weight, "Missed target again: drop the weight.", missed=True
        )

    # 2. Target hit. If RPE wasn't logged, treat it like RPE 10: be cautious.
    if rpe is not None and rpe < 10:
        return Recommendation(
            "increase", weight + INCREMENT_KG[size], f"Hit target at RPE {rpe:g}: increase."
        )

    # 3. Target hit at RPE 10 (or unknown): repeat by default, small bump as an option.
    return Recommendation(
        "repeat",
        weight,
        "Hit target but at RPE 10: repeat the block, or take a small increase.",
        alternatives=[("increase", weight + RPE10_OPTION_KG)],
    )


def next_miss_count(recommendation, consecutive_misses):
    """Update the miss counter after a block ends.

    A missed target adds one; a successful block resets the counter to 0.
    """
    return consecutive_misses + 1 if recommendation.missed else 0


def target_was_hit(target_sets, target_reps, target_weight, logged_sets):
    """Did the logged sets meet the plan?

    logged_sets: list of (weight_kg, reps) tuples from the final week.
    Hit = at least `target_sets` sets with weight >= target and reps >= target.
    """
    good_sets = [1 for w, r in logged_sets if w >= target_weight and r >= target_reps]
    return len(good_sets) >= target_sets


def plan_after_gap(missed_weeks):
    """What to do when training weeks were missed (illness, travel, exams).

    These are common coaching heuristics, not hard rules. Tune SHORT_GAP_MAX_WEEKS.
      0 weeks           -> "continue"
      short gap         -> "extend": push the schedule back, same targets
      longer gap        -> "step_back": redo earlier weeks at lighter weights
    """
    if missed_weeks <= 0:
        return "continue"
    if missed_weeks <= SHORT_GAP_MAX_WEEKS:
        return "extend"
    return "step_back"
