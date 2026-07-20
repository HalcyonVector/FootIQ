"""Unit tests for core/advanced/geometry.py's pure pitch-geometry functions —
no pandas/event-schema dependency, so these run in isolation from real data."""
import pytest

from core.advanced.geometry import (
    dist_to_goal, in_box, is_progressive_action, zone_third,
    half_space_of, defensive_zone, angle_bias, carry_directness,
    PROG_TIER_OWN_HALF_UNITS, PROG_TIER_CROSSING_UNITS, PROG_TIER_ATT_HALF_UNITS,
)


def test_dist_to_goal_at_goal_mouth_is_zero():
    assert dist_to_goal(100, 50) == 0


def test_dist_to_goal_symmetric_about_goal_y():
    # Same distance from goal whether y is above or below center, by symmetry.
    assert dist_to_goal(80, 40) == pytest.approx(dist_to_goal(80, 60))


def test_in_box_true_at_penalty_spot():
    assert in_box(89, 50) is True


def test_in_box_false_outside_box_width():
    assert in_box(90, 5) is False


def test_in_box_false_short_of_box_line():
    assert in_box(70, 50) is False


class TestIsProgressiveAction:
    def test_ending_in_box_is_always_progressive(self):
        # Even a tiny nudge that lands in the box counts, regardless of gain.
        assert is_progressive_action((85, 50), (90, 50)) is True

    def test_own_half_needs_the_largest_gain(self):
        threshold = PROG_TIER_OWN_HALF_UNITS
        assert is_progressive_action((10, 50), (10 + threshold - 1, 50)) is False
        assert is_progressive_action((10, 50), (10 + threshold + 1, 50)) is True

    def test_crossing_halves_needs_the_smallest_gain(self):
        threshold = PROG_TIER_CROSSING_UNITS
        start_x = 50 - threshold / 2
        end_x = start_x + threshold - 1
        assert is_progressive_action((start_x, 50), (end_x, 20)) is False
        end_x = start_x + threshold + 1
        assert is_progressive_action((start_x, 50), (end_x, 20)) is True

    def test_attacking_half_needs_the_middle_gain(self):
        threshold = PROG_TIER_ATT_HALF_UNITS
        assert is_progressive_action((60, 20), (60 + threshold - 1, 20)) is False
        assert is_progressive_action((60, 20), (60 + threshold + 1, 20)) is True

    def test_own_half_threshold_is_the_largest(self):
        # Sanity check on the three-tier calibration itself: progressing the
        # ball is "worth less" (needs a bigger gain to count) deep in your
        # own half than near the opponent's goal.
        assert PROG_TIER_OWN_HALF_UNITS > PROG_TIER_CROSSING_UNITS > PROG_TIER_ATT_HALF_UNITS

    def test_backward_action_is_never_progressive(self):
        assert is_progressive_action((60, 50), (40, 50)) is False


def test_zone_third_boundaries():
    assert zone_third(0) == "def"
    assert zone_third(33) == "def"
    assert zone_third(34) == "mid"
    assert zone_third(66) == "mid"
    assert zone_third(67) == "att"
    assert zone_third(100) == "att"


def test_half_space_of_left_right_and_none():
    assert half_space_of(90, 30) == "left"
    assert half_space_of(90, 70) == "right"
    assert half_space_of(90, 50) is None       # central channel, not a half-space
    assert half_space_of(90, 5) is None         # out on the flank


def test_defensive_zone_box_channel_flank_other():
    # x is already goal-relative per the docstring (0 = own goal line).
    assert defensive_zone(10, 50) == "box"        # deep and central -> own box
    assert defensive_zone(20, 30) == "channel"     # shallow, half-space strip
    assert defensive_zone(20, 5) == "flank"        # shallow, out wide
    assert defensive_zone(60, 50) == "other"       # too far upfield for any of the above


def test_angle_bias_pure_vertical_is_zero():
    assert angle_bias((50, 50), (70, 50)) == 0.0


def test_angle_bias_toward_center_is_positive():
    # Starting left of center (y=30), moving further toward y=50 is "infield".
    assert angle_bias((50, 30), (60, 45)) > 0


def test_angle_bias_toward_touchline_is_negative():
    assert angle_bias((50, 30), (60, 15)) < 0


def test_carry_directness_straight_at_goal_is_one():
    assert carry_directness((50, 50), (100, 50)) == pytest.approx(1.0)


def test_carry_directness_sideways_is_low():
    assert carry_directness((50, 50), (50, 90)) < 0.5


def test_carry_directness_zero_length_carry_is_zero():
    assert carry_directness((50, 50), (50, 50)) == 0.0
