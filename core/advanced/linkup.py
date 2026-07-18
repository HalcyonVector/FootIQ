"""
Combination Play data pipeline ("Link-Up & Synergy" in the reference app,
renamed since the UI is ours). Pairwise, not per-player: for every completed
pass from A to B, records where B received it and what B did with it next
(progressive pass / regular pass / lost it / progressive carry / take-on
won-lost / shot) — the receiver's own subsequent action, walked through the
same adjacency logic as carries.py so a brief dribble between reception and
release is captured, not just the immediate next recorded event.
"""

from core.advanced import geometry as g, qualifiers as q, timing
from core.advanced.carries import NON_TOUCH_TYPES

MAX_FOLLOWUP_SECONDS = 15.0
SHOT_TYPES = ("MissedShots", "SavedShot", "Goal", "ShotOnPost")


def compute_linkup(events: list[dict]) -> dict:
    """Returns {(passer_id, receiver_id): [reception_record, ...]}, one
    record per completed pass with a same-team receiver."""
    pairs: dict = {}

    for i, e in enumerate(events):
        if e["type"] != "Pass" or e["outcome_type"] != "Successful":
            continue
        qm = q.qmap(e["qualifiers"])
        if not q.is_open_play(qm):
            continue
        passer = e["player_id"]
        rx, ry = e.get("end_x"), e.get("end_y")
        if passer is None or rx is None or ry is None:
            continue

        nxt = events[i + 1] if i + 1 < len(events) else None
        if not nxt or nxt.get("team_id") != e["team_id"] or nxt.get("player_id") in (None, passer):
            continue
        receiver = nxt["player_id"]

        # Walk forward through the receiver's own consecutive touches (same
        # rule as carries.py) to find their eventual resulting action.
        cur = nxt
        j = i + 2
        while j < len(events):
            cand = events[j]
            if cand["type"] in NON_TOUCH_TYPES:
                j += 1
                continue
            if cand.get("player_id") != receiver or cand.get("team_id") != e["team_id"]:
                break
            if timing.event_seconds(cand) - timing.event_seconds(cur) > MAX_FOLLOWUP_SECONDS:
                break
            cur = cand
            j += 1

        outcome = _classify(rx, ry, cur)
        key = (passer, receiver)
        pairs.setdefault(key, []).append({
            "reception_x": rx, "reception_y": ry,
            "outcome": outcome["kind"],
            "end_x": outcome["end_x"], "end_y": outcome["end_y"],
        })

    return pairs


def _classify(start_x: float, start_y: float, action: dict) -> dict:
    ex, ey = action.get("end_x"), action.get("end_y")
    ax, ay = action.get("x"), action.get("y")
    end_x = ex if ex is not None else ax
    end_y = ey if ey is not None else ay

    if action["type"] == "Pass":
        if action["outcome_type"] != "Successful":
            return {"kind": "unsuccessful", "end_x": end_x, "end_y": end_y}
        qm = q.qmap(action["qualifiers"])
        if not q.has_qualifier(qm, q.CROSS_Q) and None not in (ex, ey) \
                and g.is_progressive_action((start_x, start_y), (ex, ey)):
            return {"kind": "prog_pass", "end_x": end_x, "end_y": end_y}
        return {"kind": "pass", "end_x": end_x, "end_y": end_y}

    if action["type"] == "TakeOn":
        kind = "takeon_won" if action["outcome_type"] == "Successful" else "takeon_lost"
        return {"kind": kind, "end_x": ax, "end_y": ay}

    if action["type"] in SHOT_TYPES:
        return {"kind": "shot", "end_x": ax, "end_y": ay}

    if action["type"] == "Dispossessed":
        return {"kind": "unsuccessful", "end_x": ax, "end_y": ay}

    # Any other resulting action (clearance under pressure, foul suffered,
    # etc.) — treat as a carry-and-hold rather than lost, using their
    # last known position as the resolution point.
    if ax is not None and ay is not None and g.is_progressive_action((start_x, start_y), (ax, ay)):
        return {"kind": "prog_carry", "end_x": ax, "end_y": ay}
    return {"kind": "pass", "end_x": end_x, "end_y": end_y}
