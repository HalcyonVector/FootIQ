"""
Half-Spaces — the two strips between the box width and the touchline, in
the ATTACKING half, where a receiver has the goal in front of them.
Combines passing/carrying/defending actions filtered to this zone.

(geometry.half_space_of() is a pure y-band check reused elsewhere for a
different purpose — Defending Profile's "channel" zone, which deliberately
wants the DEFENSIVE third instead. This module adds the x>=50 attacking-half
restriction itself, since that's specific to what "half-space" means here.)
"""

from core.advanced import geometry as g, qualifiers as q
from core.advanced.accumulate import PlayerAcc

P90_KEYS = {
    "hs_receptions", "hs_passes", "hs_prog_passes", "hs_carries", "hs_prog_carries",
    "hs_takeons", "hs_key_passes", "hs_shots", "hs_into_box",
    "hs_def_actions", "hs_tackles", "hs_interceptions", "hs_recoveries",
    "hs_blocks", "hs_aerials_won",
}


def _in_half_space(x, y) -> bool:
    return x is not None and y is not None and x >= 50 and g.half_space_of(x, y) is not None


def compute_half_spaces(events: list[dict], carries: list[dict]) -> dict:
    acc = PlayerAcc()

    for i, e in enumerate(events):
        pid = e["player_id"]
        if pid is None:
            continue
        etype = e["type"]
        x, y = e.get("x"), e.get("y")

        if etype == "Pass":
            qm = q.qmap(e["qualifiers"])
            if not q.is_open_play(qm):
                continue
            completed = e["outcome_type"] == "Successful"
            if _in_half_space(x, y):
                acc.add(pid, "hs_passes")
                ex, ey = e.get("end_x"), e.get("end_y")
                if completed and ex is not None and ey is not None:
                    if not q.has_qualifier(qm, q.CROSS_Q) and g.is_progressive_action((x, y), (ex, ey)):
                        acc.add(pid, "hs_prog_passes")
                    if g.in_box(ex, ey):
                        acc.add(pid, "hs_into_box")
                if q.has_qualifier(qm, q.KEY_PASS_Q):
                    acc.add(pid, "hs_key_passes")

            # reception: pass ends in half-space, next event is a teammate touching it
            ex, ey = e.get("end_x"), e.get("end_y")
            if completed and _in_half_space(ex, ey):
                nxt = events[i + 1] if i + 1 < len(events) else None
                if nxt and nxt.get("team_id") == e["team_id"] and nxt.get("player_id") not in (None, pid):
                    acc.add(nxt["player_id"], "hs_receptions")

        elif etype == "TakeOn" and _in_half_space(x, y):
            acc.add(pid, "hs_takeons")
            if e["outcome_type"] == "Successful":
                acc.add(pid, "hs_takeons_won")

        elif etype in ("MissedShots", "SavedShot", "Goal", "ShotOnPost") and _in_half_space(x, y):
            acc.add(pid, "hs_shots")

        elif etype == "Tackle" and _in_half_space(x, y):
            acc.add(pid, "hs_tackles")
            acc.add(pid, "hs_def_actions")
            if e["outcome_type"] == "Successful":
                acc.add(pid, "hs_tackles_won")

        elif etype == "Interception" and _in_half_space(x, y):
            acc.add(pid, "hs_interceptions")
            acc.add(pid, "hs_def_actions")

        elif etype == "BallRecovery" and _in_half_space(x, y):
            acc.add(pid, "hs_recoveries")
            acc.add(pid, "hs_def_actions")

        elif etype == "BlockedPass" and _in_half_space(x, y):
            acc.add(pid, "hs_blocks")
            acc.add(pid, "hs_def_actions")

        elif etype == "Aerial" and _in_half_space(x, y) and e["outcome_type"] == "Successful":
            acc.add(pid, "hs_aerials_won")

    for c in carries:
        if not _in_half_space(c["start_x"], c["start_y"]):
            continue
        acc.add(c["player_id"], "hs_carries")
        if g.is_progressive_action((c["start_x"], c["start_y"]), (c["end_x"], c["end_y"])):
            acc.add(c["player_id"], "hs_prog_carries")

    return acc.to_dict()


def finalize_half_spaces(totals: dict) -> dict:
    out = {}
    for pid, t in totals.items():
        takeon_att = t.get("hs_takeons", 0)
        tackle_att = t.get("hs_tackles", 0)
        out[pid] = {
            "hs_receptions": t.get("hs_receptions", 0),
            "hs_passes": t.get("hs_passes", 0),
            "hs_prog_passes": t.get("hs_prog_passes", 0),
            "hs_progression_rate_pct": round(100 * t.get("hs_prog_passes", 0) / t.get("hs_passes", 0), 1) if t.get("hs_passes", 0) else None,
            "hs_carries": t.get("hs_carries", 0),
            "hs_prog_carries": t.get("hs_prog_carries", 0),
            "hs_takeons": takeon_att,
            "hs_takeon_success_pct": round(100 * t.get("hs_takeons_won", 0) / takeon_att, 1) if takeon_att >= 10 else None,
            "hs_key_passes": t.get("hs_key_passes", 0),
            "hs_shots": t.get("hs_shots", 0),
            "hs_into_box": t.get("hs_into_box", 0),
            "hs_def_actions": t.get("hs_def_actions", 0),
            "hs_tackles": tackle_att,
            "hs_tackle_success_pct": round(100 * t.get("hs_tackles_won", 0) / tackle_att, 1) if tackle_att >= 10 else None,
            "hs_interceptions": t.get("hs_interceptions", 0),
            "hs_recoveries": t.get("hs_recoveries", 0),
            "hs_blocks": t.get("hs_blocks", 0),
            "hs_aerials_won": t.get("hs_aerials_won", 0),
        }
    return out
