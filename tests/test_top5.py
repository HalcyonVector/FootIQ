"""The "Top 5 leagues only" filter on Explore, the quadrant plots and the percentile scope."""
import pandas as pd

import app as app_module
from core.advanced import config, explore, quadrants


def _df():
    leagues = ["Premier League", "La Liga", "Eredivisie", "Champions League", "Serie A", "Süper Lig"]
    rows = []
    for i, lg in enumerate(leagues):
        rows.append({"whoscored_player_id": i, "player_name": f"P{i}", "team_name": "T", "league": lg, "season": "2025-26",
                     "_pos_group": "midfielder", "position": "MC", "total_minutes": 2000, "age": 25,
                     "mx": float(i), "my": float(i) * 2, "ax": float(i), "ay": float(6 - i), "az": float(i)})
    return pd.DataFrame(rows)


def test_mask_options():
    df = _df()
    assert df[config.league_mask(df, "top5")]["league"].tolist() == ["Premier League", "La Liga", "Serie A"]
    assert len(df[config.league_mask(df, "all")]) == 6 and len(df[config.league_mask(df, None)]) == 6
    assert df[config.league_mask(df, "Eredivisie")]["player_name"].tolist() == ["P2"]


def test_explore_scatter_and_rank_honour_top5():
    df = _df()
    pts = explore.scatter_points(df, "mx", "my", "2025-26", "top5", "all", 450)
    assert sorted(p["league"] for p in pts) == ["La Liga", "Premier League", "Serie A"]
    ranked = explore.rank_players(df, "mx", "2025-26", "top5", "all", 450)
    assert {r["league"] for r in ranked} == {"Premier League", "La Liga", "Serie A"}


def test_quadrant_plot_honours_top5(monkeypatch):
    preset = {"id": "t5", "title": "t", "positions": "midfielder", "question": "q", "group": "g",
              "x": {"label": "X", "cols": ["ax"], "lower": []}, "y": {"label": "Y", "cols": ["ay"], "lower": []},
              "quad": {"tr": "a", "tl": "b", "br": "c", "bl": "d"}}
    monkeypatch.setitem(quadrants.BY_ID, "t5", preset)
    res = quadrants.quadrant_points(_df(), "t5", "2025-26", "top5", "all", 450)
    assert sorted(p["name"] for p in res["points"]) == ["P0", "P1", "P4"]


def test_percentile_scope_top5_needs_a_top5_player():
    assert app_module._parse_scope({"scope": "top5"}, "Premier League") == "top5"
    assert app_module._parse_scope({"scope": "top5"}, "Eredivisie") == "all"        # not in the pool, so no top-5 ranking
    assert app_module._parse_scope({"scope": "league"}, "Eredivisie") == "league"
    assert app_module._parse_scope({}, "Premier League") == "all"


def test_scoped_df_top5_keeps_only_the_five_leagues():
    df = _df()
    sub = app_module._scoped_df(df, "La Liga", "top5")
    assert set(sub["league"]) == {"Premier League", "La Liga", "Serie A"}
    assert app_module._scoped_df(df, "La Liga", "all") is df
    app_module._SCOPED.clear()
