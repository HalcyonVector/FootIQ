"""
Per-player minutes-played for a single match, derived from the roster
(starters vs subs) plus SubstitutionOn/Off and red-card events - not a
hardcoded 90, and aware of real injury-time length via raw_loader.match_end_minute.
"""

from core.advanced.raw_loader import match_end_minute

RED_CARD_TYPES = {"Red", "SecondYellow"}


def compute_minutes_played(match_json: dict, events: list[dict], rosters: list[dict]) -> dict:
    """Returns {player_id: minutes_float} for every player who appeared."""
    end_minute = match_end_minute(match_json)

    sub_on = {}   # player_id -> minute they came on
    sub_off = {}  # player_id -> minute they came off
    red_card_minute = {}  # player_id -> minute of red/second-yellow

    for e in events:
        pid = e.get("player_id")
        if pid is None:
            continue
        minute = e.get("expanded_minute")
        if minute is None:
            minute = e.get("minute") or 0

        if e["type"] == "SubstitutionOn":
            sub_on[pid] = minute
        elif e["type"] == "SubstitutionOff":
            sub_off[pid] = minute
        elif e["type"] == "Card" and e.get("card_type") in RED_CARD_TYPES:
            # first red only
            if pid not in red_card_minute:
                red_card_minute[pid] = minute

    minutes = {}
    for r in rosters:
        pid = r["player_id"]
        if pid is None:
            continue

        if r["is_first_eleven"]:
            start = 0.0
        elif pid in sub_on:
            start = float(sub_on[pid])
        else:
            # in the roster but never subbed on and not a starter -> unused sub, 0 minutes
            minutes[pid] = 0.0
            continue

        if pid in sub_off:
            stop = float(sub_off[pid])
        elif pid in red_card_minute:
            stop = float(red_card_minute[pid])
        else:
            stop = end_minute

        minutes[pid] = max(0.0, stop - start)

    return minutes
