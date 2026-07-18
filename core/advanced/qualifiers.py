"""
Helpers for reading Opta/WhoScored event qualifiers.

Each event's `qualifiers` field is a list of {"type": {"displayName": str}, "value": str|None}.
Most of what the reference glossary treats as "derived" metrics (assists, key passes,
crosses, through balls, shot footedness, set-piece vs open-play, big chances) are
actually just qualifier tags already present on the raw event - this module is the
single place that reads them, so category modules never touch the raw qualifiers list directly.
"""

from typing import Optional


def qmap(qualifiers: list) -> dict:
    """Flatten an event's qualifiers list into {displayName: value_or_None}."""
    out = {}
    for q in qualifiers or []:
        name = q.get("type", {}).get("displayName")
        if name:
            out[name] = q.get("value")
    return out


def has_qualifier(qmap_: dict, name: str) -> bool:
    return name in qmap_


def qualifier_value(qmap_: dict, name: str) -> Optional[str]:
    return qmap_.get(name)


def qualifier_float(qmap_: dict, name: str) -> Optional[float]:
    v = qmap_.get(name)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── Named qualifier-name sets (single source of truth for the exact strings) ──

SET_PIECE_QUALIFIERS = {
    "FreekickTaken", "CornerTaken", "ThrowIn", "GoalKick",
    "FromCorner", "KeeperThrow", "IndirectFreekickTaken", "SetPiece",
}
# Presence of ANY of these means the event is set-piece / dead-ball, not open play.

BODY_PART_QUALIFIERS = ("RightFoot", "LeftFoot", "Head", "OtherBodyPart")

CROSS_Q = "Cross"
THROUGHBALL_Q = "Throughball"
KEY_PASS_Q = "KeyPass"
ASSIST_Q = "IntentionalGoalAssist"  # pass that led directly to a goal
PRE_ASSIST_Q = "IntentionalAssist"  # pass that led to a shot/chance (not necessarily a goal)
SHOT_ASSIST_Q = "ShotAssist"        # pass that led directly to a shot
BIG_CHANCE_Q = "BigChance"
BIG_CHANCE_CREATED_Q = "BigChanceCreated"
LONGBALL_Q = "Longball"
CHIPPED_Q = "Chipped"
LAYOFF_Q = "LayOff"
ZONE_Q = "Zone"
PASS_END_X_Q = "PassEndX"
PASS_END_Y_Q = "PassEndY"
OWN_GOAL_Q = "OwnGoal"


def is_open_play(qmap_: dict) -> bool:
    return not any(sp in qmap_ for sp in SET_PIECE_QUALIFIERS)


def body_part(qmap_: dict) -> Optional[str]:
    for bp in BODY_PART_QUALIFIERS:
        if bp in qmap_:
            return bp
    return None
