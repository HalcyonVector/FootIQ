"""
Timestamp helpers. expanded_minute is the continuous, stoppage-time-aware
match clock (unlike minute/period which can behave oddly around halftime),
so it's the right basis for release-time / tempo calculations.
"""

MAX_RELEASE_GAP_SECONDS = 20.0  # beyond this, treat as a "fresh" possession, not a release


def event_seconds(e: dict) -> float:
    em = e.get("expanded_minute")
    if em is None:
        em = e.get("minute") or 0
    return float(em) * 60.0 + float(e.get("second") or 0)


def release_times_by_player(events: list[dict]) -> dict:
    """For each Pass event, the time between that player's PREVIOUS event
    (their last touch - when they gained/had the ball) and this pass (when
    they released it). Returns {event_id: release_seconds}, only for passes
    where a plausible prior touch exists within MAX_RELEASE_GAP_SECONDS.
    Sequential single pass over the match's events (already time-ordered)."""
    last_event_time: dict = {}   # player_id -> seconds of their last event
    release: dict = {}           # event_id -> release_seconds

    for e in events:
        pid = e.get("player_id")
        if pid is None:
            continue
        t = event_seconds(e)

        if e["type"] == "Pass":
            prev_t = last_event_time.get(pid)
            if prev_t is not None:
                gap = t - prev_t
                if 0 <= gap <= MAX_RELEASE_GAP_SECONDS:
                    release[e["event_id"]] = gap

        last_event_time[pid] = t

    return release
