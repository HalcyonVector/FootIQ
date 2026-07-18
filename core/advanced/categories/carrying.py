"""
Carrying Profile. Carries come from core.advanced.carries.derive_carries()
(capped at 20s per that module). Angle bias is measured on progressive
carries only, per the reference glossary.
"""

from core.advanced import geometry as g
from core.advanced.accumulate import PlayerAcc

P90_KEYS = {
    "carry_prog_count", "carry_penetration_gain_m", "carry_into_box_count",
    "carry_takeons_attempted", "carry_distance_sum_m",
}


def compute_carrying(carries: list[dict]) -> dict:
    acc = PlayerAcc()

    for c in carries:
        pid = c["player_id"]
        start = (c["start_x"], c["start_y"])
        end = (c["end_x"], c["end_y"])

        acc.add(pid, "carry_count")
        dist_m = g.units_to_meters(((end[0]-start[0])**2 + (end[1]-start[1])**2) ** 0.5)
        acc.add(pid, "carry_distance_sum_m", dist_m)

        if g.is_progressive_action(start, end):
            acc.add(pid, "carry_prog_count")
            gain_m = g.units_to_meters(max(0.0, g.dist_to_goal(*start) - g.dist_to_goal(*end)))
            acc.add(pid, "carry_penetration_gain_m", gain_m)
            bias = g.angle_bias(start, end)
            acc.append(pid, "carry_angle_bias", bias)

        if g.in_box(*end):
            acc.add(pid, "carry_into_box_count")

        acc.append(pid, "carry_directness", g.carry_directness(start, end))

    return acc.to_dict()


def compute_takeons(events: list[dict]) -> dict:
    acc = PlayerAcc()
    for e in events:
        if e["type"] != "TakeOn":
            continue
        pid = e["player_id"]
        if pid is None:
            continue
        acc.add(pid, "carry_takeons_attempted")
        if e["outcome_type"] == "Successful":
            acc.add(pid, "carry_takeons_won")
    return acc.to_dict()


def finalize_carrying(totals: dict) -> dict:
    import statistics

    out = {}
    for pid, t in totals.items():
        count = t.get("carry_count", 0)
        prog = t.get("carry_prog_count", 0)
        takeon_att = t.get("carry_takeons_attempted", 0)
        takeon_won = t.get("carry_takeons_won", 0)
        angle_list = t.get("list__carry_angle_bias", [])
        directness_list = t.get("list__carry_directness", [])

        out[pid] = {
            "carry_prog_count": prog,
            "carry_penetration_gain_m": round(t.get("carry_penetration_gain_m", 0), 1),
            "carry_into_box_count": t.get("carry_into_box_count", 0),
            "carry_takeons_attempted": takeon_att,
            "carry_takeon_success_pct": round(100 * takeon_won / takeon_att, 1) if takeon_att >= 15 else None,
            "carry_mean_distance_m": round(t.get("carry_distance_sum_m", 0) / count, 2) if count else None,
            "carry_distance_sum_m": round(t.get("carry_distance_sum_m", 0), 1),
            "carry_angle_bias_index": round(statistics.mean(angle_list), 2) if angle_list else None,
            "carry_directness": round(statistics.mean(directness_list), 2) if directness_list else None,
        }
    return out
