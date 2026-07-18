"""
Carries aren't a raw Opta event type — they're derived as the gap between a
player's own consecutive ball-involvement events, when nothing else happens
in between (no intervening event, i.e. the two events are strictly adjacent
in the match's chronological event stream). This is the standard technique
used across the football-analytics community for exactly this reason.

Administrative event types (subs, cards, formation changes, restarts) are
excluded from being carry endpoints since they don't represent a real
ball touch location.
"""

from core.advanced import geometry as g, timing

NON_TOUCH_TYPES = {
    "Card", "SubstitutionOn", "SubstitutionOff", "FormationChange",
    "FormationSet", "Start", "End", "OffsideGiven", "OffsideProvoked",
    "CornerAwarded",
}

MAX_CARRY_SECONDS = 20.0
MIN_CARRY_DISTANCE_UNITS = 2.0  # ignore negligible shuffles (~2m)


def derive_carries(events: list[dict]) -> list[dict]:
    """Returns a list of carry dicts: {player_id, team_id, start_x, start_y,
    end_x, end_y, duration_s, period}, one per detected carry."""
    carries = []
    prev = None

    for e in events:
        if e["type"] in NON_TOUCH_TYPES:
            continue
        if e.get("player_id") is None or e.get("x") is None or e.get("y") is None:
            prev = None
            continue

        if prev is not None and prev["player_id"] == e["player_id"] and prev["team_id"] == e["team_id"] \
                and prev["period"] == e["period"]:
            dt = timing.event_seconds(e) - timing.event_seconds(prev)
            if 0 <= dt <= MAX_CARRY_SECONDS:
                straight_dist = ((e["x"] - prev["x"]) ** 2 + (e["y"] - prev["y"]) ** 2) ** 0.5
                if straight_dist >= MIN_CARRY_DISTANCE_UNITS:
                    carries.append({
                        "player_id": e["player_id"],
                        "team_id": e["team_id"],
                        "start_x": prev["x"], "start_y": prev["y"],
                        "end_x": e["x"], "end_y": e["y"],
                        "duration_s": round(dt, 2),
                        "period": e["period"],
                    })

        prev = e

    return carries
