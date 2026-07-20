"""
Player search + identity, backed directly by the advanced (WhoScored-derived)
parquet — replaces the old CSV-backed core/fetcher.py now that the FBref
dataset has been retired. whoscored_player_id IS the player_id everywhere
now; no more synthetic hash-based ID translation layer.
"""

import pandas as pd

from core.advanced.store import get_advanced_df
from core.media import _normalize_str, get_team_color


def _clean_position(value) -> str:
    return value if isinstance(value, str) and value else "Unknown"


def _clean_minutes(value) -> int:
    # NaN is truthy in Python (`if float('nan')` is True), so a naive
    # `if value else 0` lets a missing/NaN total_minutes slip through as-is —
    # round(nan) then raises, and even if it didn't, a bare NaN serializes to
    # a bare `NaN` token in the JSON response, which browsers' JSON.parse
    # rejects outright (unlike Python's own permissive json module).
    return round(value) if value and not pd.isna(value) else 0


def _clean_age(value) -> int | None:
    """None (not 0/NaN) when unknown — age is genuinely optional (a player
    might never have a roster entry with it recorded), unlike minutes."""
    if value is None or pd.isna(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _row_to_dict(row) -> dict:
    return {
        "id": int(row["whoscored_player_id"]),
        "name": row["player_name"],
        "team": row["team_name"],
        "league": row["league"],
        "season": row["season"],
        "position": _clean_position(row["position"]),
        "minutes": _clean_minutes(row["total_minutes"]),
        "age": _clean_age(row.get("age")),
    }


def search_players(name: str, league: str, season: str) -> list[dict]:
    df = get_advanced_df()
    if df.empty:
        return []
    norm_name = _normalize_str(name)
    mask = (
        df["player_name"].apply(lambda p: norm_name in _normalize_str(str(p)))
        & (df["league"] == league)
        & (df["season"] == season)
    )
    return [_row_to_dict(r) for _, r in df[mask].head(15).iterrows()]


def search_players_global(name: str, season: str) -> list[dict]:
    df = get_advanced_df()
    if df.empty:
        return []
    norm_name = _normalize_str(name)
    mask = df["player_name"].apply(lambda p: norm_name in _normalize_str(str(p))) & (df["season"] == season)
    return [_row_to_dict(r) for _, r in df[mask].head(15).iterrows()]


def search_players_by_league(league: str, season: str, page: int = 1) -> list[dict]:
    df = get_advanced_df()
    if df.empty:
        return []
    mask = (df["league"] == league) & (df["season"] == season)
    subset = df[mask].sort_values("total_minutes", ascending=False)
    start = (page - 1) * 20
    return [_row_to_dict(r) for _, r in subset.iloc[start:start + 20].iterrows()]


def get_player_stats(player_id: int, league: str, season: str) -> dict | None:
    """Fetch a player's row by whoscored_player_id + league + season."""
    df = get_advanced_df()
    if df.empty:
        return None
    match = df[(df["whoscored_player_id"] == int(player_id)) & (df["league"] == league) & (df["season"] == season)]
    if match.empty:
        # fall back to any season for this league (player might not have a row this season)
        match = df[(df["whoscored_player_id"] == int(player_id)) & (df["league"] == league)]
    if match.empty:
        return None

    row = match.iloc[0]
    name = row["player_name"]
    team = row["team_name"]

    return {
        "id": int(row["whoscored_player_id"]),
        "name": name,
        # No photo fetch here — the frontend lazy-loads it client-side via
        # /api/player-image right after this response arrives (see
        # renderProfileHeader's applyWikiImage call), same as Compare/Scout.
        # This used to call get_wikimedia_image() synchronously, which meant
        # every single player selection paid the full Wikipedia round-trip
        # cost before showing ANY stats, even though the result was always
        # immediately overwritten by that client-side re-fetch anyway.
        "photo": "",
        "team": team,
        "team_color": get_team_color(team),
        "league": row["league"],
        "season": row["season"],
        "position": _clean_position(row["position"]),
        "minutes": _clean_minutes(row["total_minutes"]),
        "age": _clean_age(row.get("age")),
    }
