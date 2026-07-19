"""
Aerial Duels. Duel pairs are linked via the OppositeRelatedEvent qualifier
(resolved through the small per-match eventId, not the global event id —
see possession_chains.index_by_seq). For the winner of each duel, a 6-event
forward trace determines what happens to the ball next: AQ points
(+2 self, +1 teammate, -1 opponent), "retains & plays" (skipping over an
immediate clearance if there is one), and passes/shots taken off the duel.
"""

from core.advanced import geometry as g, qualifiers as q
from core.advanced.accumulate import PlayerAcc
from core.advanced.possession_chains import trace_forward

P90_KEYS = {
    "aer_duels_count", "aer_passes_off_duel", "aer_prog_passes_off_duel", "aer_shots_off_duel",
    "aer_duels_att_third",
}


def compute_aerial(events: list[dict]) -> dict:
    acc = PlayerAcc()

    for i, e in enumerate(events):
        if e["type"] != "Aerial":
            continue
        pid = e["player_id"]
        if pid is None:
            continue

        qm = q.qmap(e["qualifiers"])
        is_set_piece = not q.is_open_play(qm)
        won = e["outcome_type"] == "Successful"
        x = e.get("x")

        acc.add(pid, "aer_duels")
        if is_set_piece:
            acc.add(pid, "aer_duels_sp")
            if won:
                acc.add(pid, "aer_won_sp")
        else:
            acc.add(pid, "aer_duels_op")
            if won:
                acc.add(pid, "aer_won_op")

        if x is not None and x >= 200 / 3:
            acc.add(pid, "aer_duels_att_third")

        if not won:
            continue

        # ── Outcome trace for the WINNER only ──
        trace = trace_forward(events, i, max_depth=6)
        if not trace:
            continue

        # Skip past: (a) other Aerial/Challenge events from the SAME contested
        # duel — Opta logs one event per player involved, so the immediate
        # "next" event is very often just the loser's mirrored record of this
        # same jump, not a genuine subsequent action — and (b) an immediate
        # clearance by the winner's own team, to find the first real
        # "controlling touch."
        controlling = None
        cleared_out = False
        for k, te in enumerate(trace):
            if te["type"] in ("Aerial", "Challenge"):
                continue
            if te["type"] == "Clearance" and te.get("team_id") == e["team_id"]:
                # peek at what follows the clearance to see if it went out of play
                if k + 1 < len(trace):
                    nxt = trace[k + 1]
                    nxt_qm = q.qmap(nxt["qualifiers"])
                    if nxt.get("team_id") != e["team_id"] and any(
                        q.has_qualifier(nxt_qm, sp) for sp in ("ThrowIn", "GoalKick")
                    ) or nxt["type"] == "CornerAwarded":
                        cleared_out = True
                continue
            controlling = te
            break

        acc.add(pid, "aer_won_duels")
        if controlling is None:
            if cleared_out:
                acc.add(pid, "aer_cleared_out")
            continue

        same_team = controlling.get("team_id") == e["team_id"]
        is_self = controlling.get("player_id") == pid

        if is_self:
            acc.add(pid, "aer_aq_points", 2)
            acc.add(pid, "aer_retains_plays")
        elif same_team:
            acc.add(pid, "aer_aq_points", 1)
            acc.add(pid, "aer_falls_teammate")
        else:
            acc.add(pid, "aer_aq_points", -1)
            acc.add(pid, "aer_falls_opponent")

        if is_self and controlling["type"] == "Pass":
            acc.add(pid, "aer_passes_off_duel")
            cqm = q.qmap(controlling["qualifiers"])
            cx, cy = controlling.get("x"), controlling.get("y")
            cex, cey = controlling.get("end_x"), controlling.get("end_y")
            completed = controlling["outcome_type"] == "Successful"
            if completed:
                acc.add(pid, "aer_passes_off_duel_completed")
            if completed and None not in (cx, cy, cex, cey) \
                    and not q.has_qualifier(cqm, q.CROSS_Q) and g.is_progressive_action((cx, cy), (cex, cey)):
                acc.add(pid, "aer_prog_passes_off_duel")
        elif is_self and controlling["type"] in ("MissedShots", "SavedShot", "Goal", "ShotOnPost"):
            acc.add(pid, "aer_shots_off_duel")

    return acc.to_dict()


def finalize_aerial(totals: dict) -> dict:
    out = {}
    for pid, t in totals.items():
        won_duels = t.get("aer_won_duels", 0)
        duels_op = t.get("aer_duels_op", 0)
        duels_sp = t.get("aer_duels_sp", 0)
        out[pid] = {
            "aer_duels_count": t.get("aer_duels", 0),
            "aer_win_rate_op_pct": round(100 * t.get("aer_won_op", 0) / duels_op, 1) if duels_op >= 10 else None,
            "aer_win_rate_sp_pct": round(100 * t.get("aer_won_sp", 0) / duels_sp, 1) if duels_sp >= 5 else None,
            "aer_aq_points_per_duel": round(t.get("aer_aq_points", 0) / won_duels, 2) if won_duels >= 10 else None,
            "aer_duel_quality_pct": round(100 * (t.get("aer_retains_plays", 0) + t.get("aer_falls_teammate", 0)) / won_duels, 1) if won_duels >= 10 else None,
            "aer_retains_plays_pct": round(100 * t.get("aer_retains_plays", 0) / won_duels, 1) if won_duels >= 10 else None,
            "aer_falls_teammate_pct": round(100 * t.get("aer_falls_teammate", 0) / won_duels, 1) if won_duels >= 10 else None,
            "aer_falls_opponent_pct": round(100 * t.get("aer_falls_opponent", 0) / won_duels, 1) if won_duels >= 10 else None,
            "aer_cleared_out_pct": round(100 * t.get("aer_cleared_out", 0) / won_duels, 1) if won_duels >= 10 else None,
            "aer_passes_off_duel": t.get("aer_passes_off_duel", 0),
            "aer_post_aerial_accuracy_pct": round(100 * t.get("aer_passes_off_duel_completed", 0) / t.get("aer_passes_off_duel", 0), 1) if t.get("aer_passes_off_duel", 0) >= 10 else None,
            "aer_prog_passes_off_duel": t.get("aer_prog_passes_off_duel", 0),
            "aer_shots_off_duel": t.get("aer_shots_off_duel", 0),
            "aer_duels_att_third": t.get("aer_duels_att_third", 0),
        }
    return out
