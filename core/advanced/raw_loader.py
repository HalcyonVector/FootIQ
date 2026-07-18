"""
Loads raw WhoScored match-event JSON directly (no soccerdata reader classes -
those spin up a real Selenium/Chrome instance on construction and can trigger
live network calls for the current season even for "cached" reads).
"""

import json
import os
from pathlib import Path
from typing import Iterator

from core.advanced import config


def iter_match_files(league: str, season: str) -> Iterator[Path]:
    d = config.match_dir(league, season)
    if not os.path.isdir(d):
        return
    for name in sorted(os.listdir(d)):
        if name.endswith(".json"):
            yield Path(d) / name


def load_match_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_rosters(match_json: dict) -> list[dict]:
    """One row per player who appeared for either team, with match-level metadata."""
    rows = []
    for side in ("home", "away"):
        team = match_json.get(side)
        if not team:
            continue
        team_id = team.get("teamId")
        team_name = team.get("name")
        for p in team.get("players", []):
            rows.append({
                "player_id": p.get("playerId"),
                "player_name": p.get("name"),
                "team_id": team_id,
                "team_name": team_name,
                "side": side,
                "position": p.get("position"),
                "age": p.get("age"),
                "is_first_eleven": p.get("isFirstEleven", False),
                "shirt_no": p.get("shirtNo"),
            })
    return rows


def parse_events(match_json: dict) -> list[dict]:
    """Flatten events[] to plain dicts. Qualifiers kept as the raw list (callers
    should run qualifiers.qmap() on it once per event, not per lookup)."""
    out = []
    for e in match_json.get("events", []):
        out.append({
            "event_id": e.get("id"),
            "seq_id": e.get("eventId"),  # small per-match counter; RelatedEventId/OppositeRelatedEvent reference THIS, not "id"
            "period": (e.get("period") or {}).get("displayName"),
            "minute": e.get("minute"),
            "second": e.get("second") or 0,
            "expanded_minute": e.get("expandedMinute"),
            "type": (e.get("type") or {}).get("displayName"),
            "outcome_type": (e.get("outcomeType") or {}).get("displayName"),
            "team_id": e.get("teamId"),
            "player_id": e.get("playerId"),
            "x": e.get("x"),
            "y": e.get("y"),
            "end_x": e.get("endX"),
            "end_y": e.get("endY"),
            "qualifiers": e.get("qualifiers") or [],
            "is_touch": e.get("isTouch", False),
            "is_shot": e.get("isShot", False),
            "is_goal": e.get("isGoal", False),
            "card_type": (e.get("cardType") or {}).get("displayName") if e.get("cardType") else None,
        })
    return out


def match_end_minute(match_json: dict) -> float:
    """Real match-end minute (injury time aware), not a hardcoded 90.
    Prefers periodEndMinutes (the actual last playing minute of the final
    period) over expandedMaxMinute, which pads in a "PostGame" placeholder
    period and overstates the real minute count."""
    period_ends = match_json.get("periodEndMinutes") or {}
    if period_ends:
        try:
            return float(max(period_ends.values()))
        except (TypeError, ValueError):
            pass
    v = match_json.get("maxMinute")
    if v:
        return float(v)
    return 90.0


def player_name_dict(match_json: dict) -> dict:
    """{player_id(int): name} from the match's own lookup table."""
    return {int(k): v for k, v in (match_json.get("playerIdNameDictionary") or {}).items()}
