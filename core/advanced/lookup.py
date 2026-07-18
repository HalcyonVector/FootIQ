"""
Player search + identity, backed directly by the advanced (WhoScored-derived)
parquet — replaces the old CSV-backed core/fetcher.py now that the FBref
dataset has been retired. whoscored_player_id IS the player_id everywhere
now; no more synthetic hash-based ID translation layer.
"""

from core.advanced.store import get_advanced_df
from core.media import _normalize_str, get_team_color, get_wikimedia_image


def _row_to_dict(row) -> dict:
    return {
        "id": int(row["whoscored_player_id"]),
        "name": row["player_name"],
        "team": row["team_name"],
        "league": row["league"],
        "season": row["season"],
        "position": row["position"] if row["position"] else "Unknown",
        "minutes": round(row["total_minutes"]) if row["total_minutes"] else 0,
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
    photo = get_wikimedia_image(name, team=team)

    return {
        "id": int(row["whoscored_player_id"]),
        "name": name,
        "photo": photo,
        "team": team,
        "team_color": get_team_color(team),
        "league": row["league"],
        "season": row["season"],
        "position": row["position"] if row["position"] else "Unknown",
        "minutes": round(row["total_minutes"]) if row["total_minutes"] else 0,
    }
