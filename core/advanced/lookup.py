"""
Player search + identity, backed directly by the advanced (WhoScored-derived)
parquet — replaces the old CSV-backed core/fetcher.py now that the FBref
dataset has been retired. whoscored_player_id IS the player_id everywhere
now; no more synthetic hash-based ID translation layer.
"""

import re

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


# ── Name search index ─────────────────────────────────────────────────────────
# Searching used to run a pandas string-contains over every one of the ~36k
# player-season rows (plus league/season compares and iterrows) on EVERY
# keystroke -- cheap on a laptop, slow on Render's 0.1 CPU. The index is built
# once per loaded dataset: one tuple per row, grouped by (league, season) and by
# season, so a query only scans the few hundred names that could match and
# ranks them (name starts with the query, then a word starts with it, then
# anywhere; busiest players first within each).
_SEARCH_IDX: dict = {"df": None, "by_ls": {}, "by_s": {}}
_SEARCH_COLS = ["_norm_name", "whoscored_player_id", "player_name", "team_name", "league", "season",
                "position", "total_minutes", "age"]


def _search_index() -> dict:
    df = get_advanced_df()
    if _SEARCH_IDX["df"] is df:
        return _SEARCH_IDX
    by_ls: dict = {}
    by_s: dict = {}
    if not df.empty:
        for t in zip(*(df[c].tolist() for c in _SEARCH_COLS)):
            if not isinstance(t[0], str):
                continue
            by_ls.setdefault((t[4], t[5]), []).append(t)
            by_s.setdefault(t[5], []).append(t)
    _SEARCH_IDX.update(df=df, by_ls=by_ls, by_s=by_s)
    return _SEARCH_IDX


def build_search_index() -> None:
    """Called from the boot warm-up so the first keystroke doesn't pay for it."""
    _search_index()


def _tuple_to_dict(t: tuple) -> dict:
    return {
        "id": int(t[1]), "name": t[2], "team": t[3], "league": t[4], "season": t[5],
        "position": _clean_position(t[6]), "minutes": _clean_minutes(t[7]), "age": _clean_age(t[8]),
    }


def _match_rank(name: str, query: str, i: int) -> int:
    """0 = a whole word of the name IS the query ('salah' -> Mohamed Salah), 1 = name starts
    with it, 2 = a word starts with it, 3 = somewhere inside a word."""
    if query in re.split(r"[ \-]", name):
        return 0
    if i == 0:
        return 1
    return 2 if name[i - 1] in " -" else 3


def _ranked_matches(pool: list, query: str, limit: int = 15) -> list[dict]:
    hits = []
    for t in pool:
        n = t[0]
        i = n.find(query)
        if i < 0:
            continue
        rank = _match_rank(n, query, i)
        mins = t[7]
        hits.append((rank, -(mins if mins == mins and mins is not None else 0), n, t))
    hits.sort(key=lambda h: h[:3])
    return [_tuple_to_dict(h[3]) for h in hits[:limit]]


def search_players(name: str, league: str, season: str) -> list[dict]:
    query = _normalize_str(name)
    if not query:
        return []
    return _ranked_matches(_search_index()["by_ls"].get((league, season), []), query)


def search_players_global(name: str, season: str) -> list[dict]:
    query = _normalize_str(name)
    if not query:
        return []
    return _ranked_matches(_search_index()["by_s"].get(season, []), query)


def search_players_any(name: str, limit: int = 15) -> list[dict]:
    """Search across every season and league; each player appears once, on their
    newest season (the hub search box: 'find this player', no season picker)."""
    from core.advanced.config import season_sort_key
    query = _normalize_str(name)
    if not query:
        return []
    best: dict = {}
    total: dict = {}     # minutes across every season: a better "who is this person" signal than one season
    for season, pool in _search_index()["by_s"].items():
        sk = season_sort_key(season)
        for t in pool:
            i = t[0].find(query)
            if i < 0:
                continue
            mins = t[7] if (t[7] == t[7] and t[7] is not None) else 0
            total[t[1]] = total.get(t[1], 0) + mins
            key = (sk, mins)
            cur = best.get(t[1])
            if cur is None or key > cur[0]:
                best[t[1]] = (key, _match_rank(t[0], query, i), t)
    hits = sorted(best.items(), key=lambda kv: (kv[1][1], -total[kv[0]]))
    return [_tuple_to_dict(kv[1][2]) for kv in hits[:limit]]


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


def get_season_progress(league: str, season: str) -> float:
    """Share of this league-season played so far (1.0 = finished, or data predates the column)."""
    df = get_advanced_df()
    if df.empty or "season_progress" not in df.columns:
        return 1.0
    rows = df[(df["league"] == league) & (df["season"] == season)]["season_progress"].dropna()
    return float(rows.iloc[0]) if len(rows) else 1.0


def get_player_seasons(player_id: int) -> list[dict]:
    """Every (league, season) this player has a row for, newest first --
    powers the profile's season switcher."""
    from core.advanced.config import season_sort_key
    df = get_advanced_df()
    if df.empty:
        return []
    rows = df[df["whoscored_player_id"] == int(player_id)]
    out = [{
        "league": r["league"], "season": r["season"],
        "team": r["team_name"], "minutes": _clean_minutes(r["total_minutes"]),
    } for _, r in rows.iterrows()]
    out.sort(key=lambda s: (season_sort_key(s["season"]), s["minutes"]), reverse=True)
    return out
