"""League-scoped percentiles: the cohort a player is ranked against shrinks to their own competition."""
import pandas as pd

import app as flask_app
from core.advanced import percentiles


def _df():
    rows = []
    for lg, base in (("Premier League", 10), ("La Liga", 50)):
        for i in range(8):
            rows.append({"league": lg, "season": "2025-26", "_pos_group": "midfielder", "total_minutes": 2000.0,
                         "whoscored_player_id": len(rows), "metric": base + i})
    return pd.DataFrame(rows)


def test_all_scope_returns_the_same_table_and_league_scope_only_that_league():
    df = _df()
    assert flask_app._scoped_df(df, "La Liga", "all") is df
    sub = flask_app._scoped_df(df, "La Liga", "league")
    assert set(sub["league"]) == {"La Liga"} and len(sub) == 8
    assert flask_app._scoped_df(df, "La Liga", "league") is sub        # the subset is reused, not rebuilt


def test_the_same_value_ranks_differently_in_a_league_cohort():
    df = _df()
    value = 12                       # a Premier League number
    everyone = percentiles.build_cohort(df, "MC", "2025-26")["metric"]
    league_only = percentiles.build_cohort(flask_app._scoped_df(df, "Premier League", "league"), "MC", "2025-26")["metric"]
    assert percentiles._percentile_rank(value, everyone) < percentiles._percentile_rank(value, league_only)   # 12 beats few of 16, but 2 of 8
