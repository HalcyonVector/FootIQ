"""Player name search index (core/advanced/lookup.py)."""
import pandas as pd

from core.advanced import lookup


def _frame(rows):
    df = pd.DataFrame(rows, columns=["player_name", "whoscored_player_id", "team_name", "league", "season", "position", "total_minutes", "age"])
    df["_norm_name"] = df["player_name"].map(lambda n: lookup._normalize_str(n))
    return df


def _use(monkeypatch, df):
    monkeypatch.setattr(lookup, "get_advanced_df", lambda: df)
    lookup._SEARCH_IDX["df"] = None     # force a rebuild for the fake frame


def test_ranks_prefix_then_word_start_then_substring(monkeypatch):
    _use(monkeypatch, _frame([
        ("Aaron Wan-Bissaka", 1, "A", "Premier League", "2025-26", "DF", 2000, 27),
        ("Bukayo Saka", 2, "B", "Premier League", "2025-26", "FW", 1500, 24),
        ("Sakai Hiroki", 3, "C", "Premier League", "2025-26", "DF", 900, 26),
    ]))
    names = [r["name"] for r in lookup.search_players("saka", "Premier League", "2025-26")]
    assert names == ["Sakai Hiroki", "Bukayo Saka", "Aaron Wan-Bissaka"]   # prefix, word start, then inside a word


def test_busier_player_first_within_a_rank(monkeypatch):
    _use(monkeypatch, _frame([
        ("Ben Low", 1, "A", "Premier League", "2025-26", "FW", 100, 20),
        ("Ben High", 2, "A", "Premier League", "2025-26", "FW", 3000, 20),
    ]))
    assert [r["id"] for r in lookup.search_players("ben", "Premier League", "2025-26")] == [2, 1]


def test_league_and_season_scoping_and_accents(monkeypatch):
    _use(monkeypatch, _frame([
        ("Hugo Ekitiké", 1, "L", "Premier League", "2025-26", "FW", 1900, 23),
        ("Hugo Ekitiké", 1, "L", "Premier League", "2024-25", "FW", 800, 22),
        ("Hugo Other", 5, "X", "La Liga", "2025-26", "FW", 700, 22),
    ]))
    assert len(lookup.search_players("ekitike", "Premier League", "2025-26")) == 1       # accent-insensitive, one season only
    assert len(lookup.search_players_global("hugo", "2025-26")) == 2                     # every league that season
    assert lookup.search_players("zzz", "Premier League", "2025-26") == []
    assert lookup.search_players("", "Premier League", "2025-26") == []
