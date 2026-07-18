"""
Shooting & Footedness — open play only. Footedness comes directly from
shot body-part qualifiers (RightFoot/LeftFoot/Head/OtherBodyPart).
"""

from core.advanced import geometry as g, qualifiers as q
from core.advanced.accumulate import PlayerAcc

P90_KEYS = {
    "shoot_shots_count", "shoot_goals_count", "shoot_sot_count",
    "shoot_in_box_count", "shoot_big_chance_count", "shoot_headed_count",
}

SHOT_TYPES = {"Goal", "MissedShots", "SavedShot", "ShotOnPost"}
ON_TARGET_TYPES = {"Goal", "SavedShot"}  # a shot saved by the keeper or scored was on target


def compute_shooting(events: list[dict], rosters: list[dict]) -> dict:
    acc = PlayerAcc()

    for e in events:
        if e["type"] not in SHOT_TYPES:
            continue
        pid = e["player_id"]
        if pid is None:
            continue

        qm = q.qmap(e["qualifiers"])
        if q.has_qualifier(qm, q.OWN_GOAL_Q):
            continue
        if not q.is_open_play(qm):
            continue

        x, y = e.get("x"), e.get("y")

        acc.add(pid, "shots")
        if e["type"] in ON_TARGET_TYPES:
            acc.add(pid, "shots_on_target")
        if e["type"] == "Goal":
            acc.add(pid, "goals")
        if x is not None and y is not None:
            if g.in_box(x, y):
                acc.add(pid, "shots_in_box")
            acc.add(pid, "shot_distance_sum_m", g.units_to_meters(g.dist_to_goal(x, y)))
        if q.has_qualifier(qm, q.BIG_CHANCE_Q):
            acc.add(pid, "shots_big_chance")

        bp = q.body_part(qm)
        if bp == "Head":
            acc.add(pid, "shots_headed")
        elif bp in ("RightFoot", "LeftFoot"):
            # weak-foot determined at finalize time against the player's dominant side
            acc.add(pid, f"shots_{bp.lower()}")
            if e["type"] == "Goal":
                acc.add(pid, f"goals_{bp.lower()}")

    return acc.to_dict()


def finalize_shooting(totals: dict) -> dict:
    out = {}
    for pid, t in totals.items():
        shots = t.get("shots", 0)
        goals = t.get("goals", 0)
        sot = t.get("shots_on_target", 0)
        rf, lf = t.get("shots_rightfoot", 0), t.get("shots_leftfoot", 0)
        rf_g, lf_g = t.get("goals_rightfoot", 0), t.get("goals_leftfoot", 0)
        foot_shots = rf + lf
        # weaker foot = whichever of L/R has fewer shots this season
        weak_shots, weak_goals = (lf, lf_g) if lf <= rf else (rf, rf_g)

        out[pid] = {
            "shoot_shots_count": shots,
            "shoot_goals_count": goals,
            "shoot_sot_count": sot,
            "shoot_in_box_count": t.get("shots_in_box", 0),
            "shoot_big_chance_count": t.get("shots_big_chance", 0),
            "shoot_headed_count": t.get("shots_headed", 0),
            "shoot_in_box_share_pct": round(100 * t.get("shots_in_box", 0) / shots, 1) if shots else None,
            "shoot_mean_distance_m": round(t.get("shot_distance_sum_m", 0) / shots, 1) if shots else None,
            "shoot_conversion_pct": round(100 * goals / shots, 1) if shots >= 12 else None,
            "shoot_accuracy_pct": round(100 * sot / shots, 1) if shots else None,
            "shoot_weak_foot_share_pct": round(100 * weak_shots / foot_shots, 1) if foot_shots else None,
            "shoot_weak_foot_conversion_pct": round(100 * weak_goals / weak_shots, 1) if weak_shots >= 12 else None,
        }
    return out
