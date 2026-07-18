"""
Decision Making. Trimmed from the reference glossary's 12 metrics to 9 —
dropped "Line-Breaker" and "Box Opener" since they're exact duplicates of
Passing Profile's progression-rate and passes-into-box, and "Execution
Quality" since its own definition ("how well decisions come off at both
quick and deliberate tempos") wasn't concrete enough to implement distinctly
from Press Resist without just re-deriving the same number under a new name.

"Time Bought" is an explicit approximation, not the literal spec (which
needs opponent/defender positions — not present in this event feed, no
freeze-frame data exists). Approximated as: how many seconds of clean touch
time the pass bought the receiver before THEIR next action, weighted by how
far up the pitch the pass landed. Labeled as an approximation in the UI.
"""

from core.advanced import geometry as g, qualifiers as q, timing
from core.advanced.accumulate import PlayerAcc
from core.advanced.possession_chains import trace_forward

P90_KEYS = {
    "dm_shot_creator", "dm_dribble_threat", "dm_direct_threat_actions",
}


def compute_decision_making(events: list[dict], carries: list[dict]) -> dict:
    acc = PlayerAcc()
    release_times = timing.release_times_by_player(events)

    for i, e in enumerate(events):
        if e["type"] != "Pass":
            continue
        pid = e["player_id"]
        if pid is None:
            continue
        qm = q.qmap(e["qualifiers"])
        if not q.is_open_play(qm):
            continue
        completed = e["outcome_type"] == "Successful"
        x, y = e.get("x"), e.get("y")
        ex, ey = e.get("end_x"), e.get("end_y")

        rel = release_times.get(e["event_id"])
        if rel is not None:
            acc.add(pid, "dm_release_sample_n")
            acc.append(pid, "dm_release_times", rel)
            if rel < 2.0:
                acc.add(pid, "dm_press_resist_attempts")
                if completed:
                    acc.add(pid, "dm_press_resist_completed")

        if completed and x is not None and ex is not None and ex > 50:
            nxt = events[i + 1] if i + 1 < len(events) else None
            if nxt and nxt.get("team_id") == e["team_id"] and nxt.get("player_id") not in (None, pid):
                acc.add(pid, "dm_space_finder_attempts")
                nx, ny = nxt.get("x"), nxt.get("y")
                if nxt["type"] not in ("Pass",) and nx is not None and ex is not None and ey is not None \
                        and g.is_progressive_action((ex, ey), (nx, ny)):
                    acc.add(pid, "dm_space_finder_hits")

                # Time Bought (approximation, see module docstring)
                nxt_rel = release_times.get(nxt.get("event_id"))
                if nxt_rel is not None:
                    weight = max(0.1, ex / 100.0)
                    acc.append(pid, "dm_time_bought", nxt_rel * weight)

                # Tempo-Setter: quick release where receiver ALSO releases quickly
                if rel is not None and rel < 1.0 and nxt_rel is not None:
                    acc.add(pid, "dm_tempo_setter_attempts")
                    if nxt_rel < 1.0:
                        acc.add(pid, "dm_tempo_setter_hits")

        if completed:
            trace = trace_forward(events, i, max_depth=2)
            if any(te["type"] in ("MissedShots", "SavedShot", "Goal", "ShotOnPost")
                   and te.get("team_id") == e["team_id"] for te in trace):
                acc.add(pid, "dm_shot_creator")

    for c in carries:
        start, end = (c["start_x"], c["start_y"]), (c["end_x"], c["end_y"])
        progressive = g.is_progressive_action(start, end)
        good_decision = progressive or g.in_box(*end)
        acc.add(c["player_id"], "dm_carries")
        if good_decision:
            acc.add(c["player_id"], "dm_carry_iq_good")
        weight = max(0.1, start[0] / 100.0)
        acc.append(c["player_id"], "dm_dribble_threat", weight)

    for e in events:
        pid = e.get("player_id")
        if pid is None or e.get("x") is None:
            continue
        if e["x"] < 200 / 3:
            continue
        if e["type"] == "TakeOn":
            acc.add(pid, "dm_direct_threat_actions")
            acc.append(pid, "dm_dribble_threat", max(0.1, e["x"] / 100.0))
        elif e["type"] in ("MissedShots", "SavedShot", "Goal", "ShotOnPost"):
            acc.add(pid, "dm_direct_threat_actions")

    return acc.to_dict()


def finalize_decision_making(totals: dict) -> dict:
    import statistics

    out = {}
    for pid, t in totals.items():
        space_att = t.get("dm_space_finder_attempts", 0)
        press_att = t.get("dm_press_resist_attempts", 0)
        tempo_att = t.get("dm_tempo_setter_attempts", 0)
        carries = t.get("dm_carries", 0)
        release_list = t.get("list__dm_release_times", [])
        time_bought_list = t.get("list__dm_time_bought", [])
        threat_list = t.get("list__dm_dribble_threat", [])

        out[pid] = {
            "dm_space_finder_pct": round(100 * t.get("dm_space_finder_hits", 0) / space_att, 1) if space_att >= 15 else None,
            "dm_time_bought_s": round(statistics.mean(time_bought_list), 2) if len(time_bought_list) >= 15 else None,
            "dm_shot_creator": t.get("dm_shot_creator", 0),
            "dm_median_release_s": round(statistics.median(release_list), 2) if release_list else None,
            "dm_press_resist_pct": round(100 * t.get("dm_press_resist_completed", 0) / press_att, 1) if press_att >= 15 else None,
            "dm_carry_iq_pct": round(100 * t.get("dm_carry_iq_good", 0) / carries, 1) if carries >= 15 else None,
            "dm_dribble_threat": round(sum(threat_list), 1) if threat_list else 0,
            "dm_tempo_setter_pct": round(100 * t.get("dm_tempo_setter_hits", 0) / tempo_att, 1) if tempo_att >= 10 else None,
            "dm_direct_threat_actions": t.get("dm_direct_threat_actions", 0),
        }
    return out
