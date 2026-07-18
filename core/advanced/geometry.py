"""
Pure pitch-geometry functions. No pandas/event-schema dependency - unit-testable
in isolation. Coordinates are the standard Opta/WhoScored 0-100 normalized pitch,
attack-direction-normalized per event (x=0 own goal line, x=100 opponent goal line,
y=0/100 the two touchlines, y=50 the pitch's horizontal center).

Progressive-pass/carry test is calibrated empirically against FBref's own
PrgP column (already sitting in football_master_with_xg.csv) rather than
guessed from a remembered textbook definition: measuring forward progress
as straight downfield (x-axis) distance gained — not Euclidean distance to
the goal mouth — with a three-tier yard threshold by which half the action
starts/ends in, correlates far better (r≈0.87 on PL 2024-25, vs r≈0.83 for
a flat %-of-distance-to-goal rule) than the naive "%cut toward goal center"
version this module started with. Crosses are excluded (they're a
different, separately-tracked action). Residual noise mostly comes from
goalkeeper long-distribution during open play (not flagged by any
qualifier) inflating a few keepers' counts — a known, accepted limitation
since progressive-passing isn't a metric users scrutinize for keepers.
"""

import math

# Standard pitch dimensions in meters, used only for converting the 0-100
# normalized coordinate system into meters for distance-based metrics
# (e.g. "Penetration gain (m)", "Mean carry distance (m)").
PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0

GOAL_X = 100.0
GOAL_Y = 50.0

BOX_X_MIN = 83.0   # opponent penalty box starts ~17m from goal line -> 100 - 17/105*100 ≈ 83.8; round for readability
BOX_Y_MIN = 21.1   # box is 40.3m wide, centered on y=50 -> 50 - 40.3/2/68*100 ≈ 20.4; using standard 18-yard-box ratio
BOX_Y_MAX = 100.0 - BOX_Y_MIN

HALF_SPACE_Y_LEFT = (BOX_Y_MIN, 36.8)     # strip between the box edge and the "central channel"
HALF_SPACE_Y_RIGHT = (63.2, BOX_Y_MAX)

OWN_HALF_X_MAX = 50.0


def dist_to_goal(x: float, y: float) -> float:
    """Straight-line distance (in 0-100 pitch units) from (x, y) to the center of the opponent goal."""
    return math.hypot(GOAL_X - x, GOAL_Y - y)


def units_to_meters(units: float) -> float:
    """Rough conversion of a 0-100-scale distance to meters (uses pitch length, the
    dominant axis for most progressive actions)."""
    return units / 100.0 * PITCH_LENGTH_M


def pct_distance_reduction(start_xy: tuple, end_xy: tuple) -> float:
    """Fraction (0-1) of the distance-to-goal eliminated by moving from start to end.
    Negative if the action moves the ball away from goal."""
    d0 = dist_to_goal(*start_xy)
    if d0 <= 0:
        return 0.0
    d1 = dist_to_goal(*end_xy)
    return (d0 - d1) / d0


def in_box(x: float, y: float) -> bool:
    return x >= BOX_X_MIN and BOX_Y_MIN <= y <= BOX_Y_MAX


PROG_TIER_OWN_HALF_UNITS = 30 / PITCH_LENGTH_M * 100     # ~30yd both ends in own half
PROG_TIER_CROSSING_UNITS = 15 / PITCH_LENGTH_M * 100     # ~15yd crossing halves
PROG_TIER_ATT_HALF_UNITS = 10 / PITCH_LENGTH_M * 100     # ~10yd both ends in attacking half


def is_progressive_action(start_xy: tuple, end_xy: tuple) -> bool:
    """Empirically-calibrated progressive test (see module docstring): forward
    (x-axis) yards gained, tiered by which half start/end fall in, OR the
    action ends in the box."""
    if in_box(*end_xy):
        return True
    x0, x1 = start_xy[0], end_xy[0]
    gain = x1 - x0
    if x0 < OWN_HALF_X_MAX and x1 < OWN_HALF_X_MAX:
        threshold = PROG_TIER_OWN_HALF_UNITS
    elif (x0 < OWN_HALF_X_MAX) != (x1 < OWN_HALF_X_MAX):
        threshold = PROG_TIER_CROSSING_UNITS
    else:
        threshold = PROG_TIER_ATT_HALF_UNITS
    return gain >= threshold


def zone_third(x: float) -> str:
    if x < 100 / 3:
        return "def"
    if x < 200 / 3:
        return "mid"
    return "att"


def half_space_of(x: float, y: float) -> str | None:
    """Returns 'left', 'right', or None if not in either half-space strip.
    Only meaningful in the attacking half/third."""
    if HALF_SPACE_Y_LEFT[0] <= y <= HALF_SPACE_Y_LEFT[1]:
        return "left"
    if HALF_SPACE_Y_RIGHT[0] <= y <= HALF_SPACE_Y_RIGHT[1]:
        return "right"
    return None


def defensive_zone(x: float, y: float) -> str:
    """For Defending Profile: which zone of the DEFENDING team's own box/channel/flank
    a defensive action happened in. Expects x already flipped so the team's own goal
    is at x=0 (i.e. call with the defending team's own-goal-relative coordinates)."""
    if in_box(100 - x, y):  # mirror in_box (which is opponent-goal-relative) onto own goal
        return "box"
    hs = half_space_of(100 - x, y)
    if hs is not None and x < 35:  # channel = half-space strip inside defensive third
        return "channel"
    if (y < BOX_Y_MIN or y > BOX_Y_MAX) and x < 35:
        return "flank"
    return "other"


def angle_bias(start_xy: tuple, end_xy: tuple) -> float:
    """Signed measure of whether a progressive carry/pass angles infield (positive)
    or out toward the touchline (negative). +1 = straight toward the center line
    (y=50), -1 = straight toward the nearest touchline, 0 = purely vertical (x-only)."""
    dx = end_xy[0] - start_xy[0]
    dy = end_xy[1] - start_xy[1]
    if dx == 0 and dy == 0:
        return 0.0
    # "infield" means y moving toward 50 from wherever it started
    toward_center = (50 - start_xy[1])
    if toward_center == 0:
        return 0.0
    infield_component = dy * (1 if toward_center > 0 else -1)
    total = math.hypot(dx, dy)
    if total == 0:
        return 0.0
    return infield_component / total


def carry_directness(start_xy: tuple, end_xy: tuple) -> float:
    """0-1: how directly a carry points at the opponent goal vs. sideways/backwards."""
    dx = end_xy[0] - start_xy[0]
    dy = end_xy[1] - start_xy[1]
    total = math.hypot(dx, dy)
    if total == 0:
        return 0.0
    to_goal_x = GOAL_X - start_xy[0]
    to_goal_y = GOAL_Y - start_xy[1]
    goal_dist = math.hypot(to_goal_x, to_goal_y)
    if goal_dist == 0:
        return 1.0
    # cosine similarity between the carry vector and the vector-to-goal, clipped to [0,1]
    dot = dx * to_goal_x + dy * to_goal_y
    cos_sim = dot / (total * goal_dist)
    return max(0.0, cos_sim)
