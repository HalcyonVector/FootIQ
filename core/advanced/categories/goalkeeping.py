"""
Goalkeeping — keepers rated on shot-stopping and distribution, not progression.
"""

from core.advanced import geometry as g, qualifiers as q
from core.advanced.accumulate import PlayerAcc

SWEEP_TYPES = {"KeeperSweeper", "Smother"}

P90_KEYS = {"gk_saves_count", "gk_goals_conceded_count", "gk_claims_count", "gk_sweeps_count"}


def compute_goalkeeping(events: list[dict], rosters: list[dict], minutes: dict) -> dict:
    acc = PlayerAcc()

    gk_team_of = {r["player_id"]: r["team_id"] for r in rosters if r["position"] == "GK"}
    # team_id -> list of (gk_player_id, minutes) for teams whose keeper(s) actually played
    gks_by_team: dict = {}
    for pid, team_id in gk_team_of.items():
        mins = minutes.get(pid, 0)
        if mins > 0:
            gks_by_team.setdefault(team_id, []).append((pid, mins))

    team_ids = list({r["team_id"] for r in rosters if r["team_id"] is not None})
    opponent_of = {}
    if len(team_ids) == 2:
        opponent_of = {team_ids[0]: team_ids[1], team_ids[1]: team_ids[0]}

    for e in events:
        pid = e["player_id"]
        etype = e["type"]
        # Save/Claim/Sweeper event types also cover outfield goal-line blocks in
        # Opta's taxonomy — gate on actual GK position so an outfielder's
        # goal-line block doesn't get counted as a goalkeeping stat.
        is_gk = pid is not None and pid in gk_team_of

        if etype == "Save" and is_gk:
            acc.add(pid, "gk_saves")
            outcome_qm = q.qmap(e["qualifiers"])
            if q.has_qualifier(outcome_qm, "DivingSave"):
                acc.add(pid, "gk_diving_saves")

        elif etype == "Claim" and is_gk:
            acc.add(pid, "gk_claims")

        elif etype in SWEEP_TYPES and is_gk:
            acc.add(pid, "gk_sweeps")
            x = e.get("x")
            if x is not None:
                acc.add(pid, "gk_sweep_distance_sum", g.units_to_meters(x))  # own-goal-relative x = how far off the line

        elif etype == "Pass" and pid is not None and pid in gk_team_of:
            qm = q.qmap(e["qualifiers"])
            acc.add(pid, "gk_dist_attempted")
            if e["outcome_type"] == "Successful":
                acc.add(pid, "gk_dist_completed")
            length = q.qualifier_float(qm, "Length")
            if length is not None and length < 30:  # short pass, roughly own-half distribution
                acc.add(pid, "gk_dist_short")

        elif etype == "Goal" and not q.has_qualifier(q.qmap(e["qualifiers"]), q.OWN_GOAL_Q):
            conceding_team = opponent_of.get(e.get("team_id"))
            keepers = gks_by_team.get(conceding_team, [])
            total_min = sum(m for _, m in keepers)
            for gk_pid, gk_min in keepers:
                weight = gk_min / total_min if total_min else 1.0 / max(len(keepers), 1)
                acc.add(gk_pid, "gk_goals_conceded", weight)

    return acc.to_dict()


def finalize_goalkeeping(totals: dict) -> dict:
    out = {}
    for pid, t in totals.items():
        saves = t.get("gk_saves", 0)
        conceded = t.get("gk_goals_conceded", 0)
        shots_faced = saves + conceded
        dist_att = t.get("gk_dist_attempted", 0)
        dist_comp = t.get("gk_dist_completed", 0)
        out[pid] = {
            "gk_save_rate_pct": round(100 * saves / shots_faced, 1) if shots_faced else None,
            "gk_saves_count": saves,
            "gk_goals_conceded_count": round(conceded, 1),
            "gk_claims_count": t.get("gk_claims", 0),
            "gk_sweeps_count": t.get("gk_sweeps", 0),
            "gk_sweep_distance": round(t.get("gk_sweep_distance_sum", 0) / t.get("gk_sweeps", 1), 1) if t.get("gk_sweeps", 0) else None,
            "gk_distribution_accuracy_pct": round(100 * dist_comp / dist_att, 1) if dist_att else None,
            "gk_plays_short_pct": round(100 * t.get("gk_dist_short", 0) / dist_att, 1) if dist_att else None,
        }
    return out
