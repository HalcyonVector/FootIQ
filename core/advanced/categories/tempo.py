"""
Tempo Control — who speeds the game up (injectors) vs who settles it (resets).
An "injector" is an action released quickly after a held touch that also
moves the ball forward/progressively; a "reset" slows the move down or
plays backwards.
"""

from core.advanced import geometry as g, qualifiers as q, timing
from core.advanced.accumulate import PlayerAcc

P90_KEYS = {
    "tempo_injectors", "tempo_injector_passes", "tempo_injector_carries",
    "tempo_resets", "tempo_injectors_into_box",
}


def compute_tempo(events: list[dict], carries: list[dict]) -> dict:
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

        rel = release_times.get(e["event_id"])
        acc.add(pid, "tempo_release_sample_n")
        if rel is not None:
            acc.append(pid, "tempo_release_times", rel)
            if rel < 1.0:
                acc.add(pid, "tempo_quick_release")

        if None in (x, y, ex, ey):
            continue
        is_forward = ex > x
        is_progressive = not q.has_qualifier(qm, q.CROSS_Q) and g.is_progressive_action((x, y), (ex, ey))

        if rel is not None and rel < 2.0 and is_forward and is_progressive:
            acc.add(pid, "tempo_injectors")
            acc.add(pid, "tempo_injector_passes")
            if completed:
                acc.add(pid, "tempo_injector_success")
                if g.in_box(ex, ey):
                    acc.add(pid, "tempo_injectors_into_box")
        elif ex < x - 5 or (rel is not None and rel > 4.0):
            acc.add(pid, "tempo_resets")

    for c in carries:
        start, end = (c["start_x"], c["start_y"]), (c["end_x"], c["end_y"])
        if c["duration_s"] < 3.0 and g.is_progressive_action(start, end):
            acc.add(c["player_id"], "tempo_injectors")
            acc.add(c["player_id"], "tempo_injector_carries")
            acc.add(c["player_id"], "tempo_injector_success")
            if g.in_box(*end):
                acc.add(c["player_id"], "tempo_injectors_into_box")

    return acc.to_dict()


def finalize_tempo(totals: dict) -> dict:
    import statistics

    out = {}
    for pid, t in totals.items():
        injectors = t.get("tempo_injectors", 0)
        resets = t.get("tempo_resets", 0)
        release_n = t.get("tempo_release_sample_n", 0)
        release_list = t.get("list__tempo_release_times", [])
        denom = injectors + resets

        out[pid] = {
            "tempo_injectors": injectors,
            "tempo_injector_passes": t.get("tempo_injector_passes", 0),
            "tempo_injector_carries": t.get("tempo_injector_carries", 0),
            "tempo_injector_success_pct": round(100 * t.get("tempo_injector_success", 0) / injectors, 1) if injectors >= 10 else None,
            "tempo_resets": resets,
            "tempo_aggression_ratio": round(injectors / denom, 2) if denom >= 10 else None,
            "tempo_injectors_into_box": t.get("tempo_injectors_into_box", 0),
            "tempo_median_release_s": round(statistics.median(release_list), 2) if release_list else None,
            "tempo_quick_release_pct": round(100 * t.get("tempo_quick_release", 0) / release_n, 1) if release_n else None,
        }
    return out
