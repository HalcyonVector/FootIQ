"""
Passing Profile — open play only (set pieces stripped via qualifiers).
Progressive-pass test follows FBref's convention (core.advanced.geometry),
not a flat "%cut" rule, so it's directly cross-checkable against the
`PrgP` column already sitting in football_master_with_xg.csv.
"""

from core.advanced import geometry as g, qualifiers as q, timing
from core.advanced.accumulate import PlayerAcc

# Output keys from finalize_passing() that are raw counts/sums and should be
# converted to per-90 rates by the aggregator (everything else is already a
# ratio/percentage/median and is used as-is).
P90_KEYS = {
    "pass_prog_count", "pass_penetration_gain_m", "pass_into_box_count",
    "pass_through_balls_count", "pass_crosses_count", "pass_key_passes_count",
    "pass_assists_count",
}


def compute_passing(events: list[dict], rosters: list[dict]) -> dict:
    acc = PlayerAcc()
    release_times = timing.release_times_by_player(events)

    for e in events:
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
        has_coords = None not in (x, y, ex, ey)

        acc.add(pid, "pass_attempted")
        if completed:
            acc.add(pid, "pass_completed")

        is_cross = q.has_qualifier(qm, q.CROSS_Q)

        if has_coords and not is_cross:
            progressive = g.is_progressive_action((x, y), (ex, ey))
            if progressive:
                acc.add(pid, "pass_prog_attempted")
                if completed:
                    acc.add(pid, "pass_prog_completed")
                    gain_m = g.units_to_meters(max(0.0, g.pct_distance_reduction((x, y), (ex, ey)) * g.dist_to_goal(x, y)))
                    acc.add(pid, "pass_penetration_gain_m", gain_m)

            if completed and g.in_box(ex, ey):
                acc.add(pid, "pass_into_box")

        if q.has_qualifier(qm, q.THROUGHBALL_Q) and completed:
            acc.add(pid, "pass_through_balls")

        if q.has_qualifier(qm, q.CROSS_Q):
            acc.add(pid, "pass_crosses_attempted")
            if completed:
                acc.add(pid, "pass_crosses_completed")

        if q.has_qualifier(qm, q.KEY_PASS_Q):
            acc.add(pid, "pass_key_passes")
        if q.has_qualifier(qm, q.ASSIST_Q):
            acc.add(pid, "pass_assists")

        rel = release_times.get(e["event_id"])
        if rel is not None:
            acc.add(pid, "pass_release_sample_n")
            acc.append(pid, "pass_release_times", rel)
            if rel < 2.0:
                acc.add(pid, "pass_release_under_2s")
            if rel < 1.0:
                acc.add(pid, "pass_release_under_1s")

    return acc.to_dict()


def finalize_passing(totals: dict) -> dict:
    """Turn one player-season's summed raw counters into the final rate/percentage
    metrics shown in the UI. min_sample gates (needs-N thresholds) return None
    below threshold so the frontend can render 'No data'."""
    import statistics

    out = {}
    for pid, t in totals.items():
        att = t.get("pass_attempted", 0)
        comp = t.get("pass_completed", 0)
        prog_att = t.get("pass_prog_attempted", 0)
        prog_comp = t.get("pass_prog_completed", 0)
        cross_att = t.get("pass_crosses_attempted", 0)
        cross_comp = t.get("pass_crosses_completed", 0)
        release_n = t.get("pass_release_sample_n", 0)
        release_list = t.get("list__pass_release_times", [])

        out[pid] = {
            "pass_prog_count": prog_comp,
            "pass_progression_rate_pct": round(100 * prog_att / att, 1) if att else None,
            "pass_prog_accuracy_pct": round(100 * prog_comp / prog_att, 1) if prog_att >= 25 else None,
            "pass_penetration_gain_m": round(t.get("pass_penetration_gain_m", 0), 1),
            "pass_into_box_count": t.get("pass_into_box", 0),
            "pass_through_balls_count": t.get("pass_through_balls", 0),
            "pass_crosses_count": cross_comp,
            "pass_cross_accuracy_pct": round(100 * cross_comp / cross_att, 1) if cross_att >= 20 else None,
            "pass_key_passes_count": t.get("pass_key_passes", 0),
            "pass_assists_count": t.get("pass_assists", 0),
            "pass_median_release_s": round(statistics.median(release_list), 2) if release_list else None,
            "pass_quick_pct": round(100 * t.get("pass_release_under_2s", 0) / release_n, 1) if release_n else None,
            "pass_one_touch_pct": round(100 * t.get("pass_release_under_1s", 0) / release_n, 1) if release_n else None,
            "pass_accuracy_pct": round(100 * comp / att, 1) if att else None,
        }
    return out
