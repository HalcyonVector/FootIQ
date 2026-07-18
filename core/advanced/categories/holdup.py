"""
Hold-Up Play — final third only, holds of 5s+. A "hold episode" is a run
of a single player's own consecutive touches (same adjacency rule as
carries.py) starting in the final third, whose total elapsed time reaches
5 seconds before the ball is released, lost, or shot.
"""

from core.advanced import geometry as g, qualifiers as q, timing
from core.advanced.accumulate import PlayerAcc
from core.advanced.carries import NON_TOUCH_TYPES
from core.advanced.possession_chains import trace_forward_by_time

MIN_HOLD_SECONDS = 5.0
FINAL_THIRD_X = 200 / 3

OPPONENT_SHOT_TYPES = ("MissedShots", "SavedShot", "Goal", "ShotOnPost")

P90_KEYS = {"hu_episodes"}


def compute_holdup(events: list[dict]) -> dict:
    acc = PlayerAcc()
    used = set()  # event indices already consumed by an episode

    i = 0
    while i < len(events):
        e = events[i]
        if i in used or e["type"] in NON_TOUCH_TYPES or e.get("player_id") is None or e.get("x") is None:
            i += 1
            continue
        if e["x"] < FINAL_THIRD_X:
            i += 1
            continue

        pid, team_id = e["player_id"], e["team_id"]
        start_t = timing.event_seconds(e)
        run = [e]
        run_indices = [i]
        j = i + 1
        while j < len(events):
            nxt = events[j]
            if nxt["type"] in NON_TOUCH_TYPES:
                j += 1
                continue
            if nxt.get("player_id") != pid or nxt.get("team_id") != team_id:
                break
            dt = timing.event_seconds(nxt) - timing.event_seconds(run[-1])
            if dt > 20.0:
                break
            run.append(nxt)
            run_indices.append(j)
            j += 1

        last = run[-1]
        duration = timing.event_seconds(last) - start_t

        if duration >= MIN_HOLD_SECONDS:
            used.update(run_indices)
            acc.add(pid, "hu_episodes")

            # what happened at the end of the hold?
            lost = last["type"] in ("Dispossessed",) or (last["type"] == "Pass" and last["outcome_type"] == "Unsuccessful")
            if not lost:
                acc.add(pid, "hu_retained")

            if last["type"] == "Pass" and last["outcome_type"] == "Successful":
                x0, y0 = e["x"], e["y"]
                ex, ey = last.get("end_x"), last.get("end_y")
                qm = q.qmap(last["qualifiers"])
                if None not in (ex, ey) and not q.has_qualifier(qm, q.CROSS_Q) and g.is_progressive_action((x0, y0), (ex, ey)):
                    acc.add(pid, "hu_prog_release")
            elif last["type"] in OPPONENT_SHOT_TYPES:
                acc.add(pid, "hu_shot_from_hold")

            if len(run) >= 2:
                x0, y0 = run[0]["x"], run[0]["y"]
                xl, yl = run[-2].get("x"), run[-2].get("y")  # last carry-position before the final action
                if xl is not None and g.is_progressive_action((x0, y0), (xl, yl)):
                    acc.add(pid, "hu_prog_carry")

            # opponent tackles attempted (and failed) against this player during the hold
            for te in events[run_indices[0]:run_indices[-1] + 1]:
                if te["type"] == "Tackle" and te.get("team_id") != team_id and te["outcome_type"] == "Unsuccessful":
                    acc.add(pid, "hu_tackles_avoided")
                if te["type"] == "Foul" and te.get("team_id") != team_id:
                    acc.add(pid, "hu_fouls_won")

            if lost:
                loss_idx = run_indices[-1]
                aftermath = trace_forward_by_time(events, loss_idx, window_seconds=10.0)
                if any(te["type"] in OPPONENT_SHOT_TYPES and te.get("team_id") != team_id for te in aftermath):
                    acc.add(pid, "hu_dangerous_loss")

        i += 1

    return acc.to_dict()


def finalize_holdup(totals: dict) -> dict:
    out = {}
    for pid, t in totals.items():
        episodes = t.get("hu_episodes", 0)
        out[pid] = {
            "hu_episodes": episodes,
            "hu_retention_pct": round(100 * t.get("hu_retained", 0) / episodes, 1) if episodes >= 10 else None,
            "hu_prog_release_pct": round(100 * t.get("hu_prog_release", 0) / episodes, 1) if episodes >= 10 else None,
            "hu_prog_carry_pct": round(100 * t.get("hu_prog_carry", 0) / episodes, 1) if episodes >= 10 else None,
            "hu_shot_from_hold_pct": round(100 * t.get("hu_shot_from_hold", 0) / episodes, 1) if episodes >= 10 else None,
            "hu_fouls_won_per_hold": round(t.get("hu_fouls_won", 0) / episodes, 2) if episodes >= 10 else None,
            "hu_tackles_avoided_per_hold": round(t.get("hu_tackles_avoided", 0) / episodes, 2) if episodes >= 10 else None,
            "hu_dangerous_loss_pct": round(100 * t.get("hu_dangerous_loss", 0) / episodes, 1) if episodes >= 10 else None,
        }
    return out
