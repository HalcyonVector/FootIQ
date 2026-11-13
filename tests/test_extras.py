"""Precomputed extras: reliability tiers, the season-to-season stability maths, and the
fallback when extras.json does not match the loaded data."""
import json

import numpy as np
import pandas as pd
import pytest

from core.advanced import extras


def test_tiers():
    assert extras.tier_for(0.85) == "high"
    assert extras.tier_for(0.70) == "high"
    assert extras.tier_for(0.62) == "medium"
    assert extras.tier_for(0.44) == "low"
    assert extras.tier_for(None) is None


def _frame(seasons, n=400, noise=0.0, seed=1):
    """n players over consecutive seasons; metric 'pass_accuracy_pct' = a fixed player trait
    plus `noise` per season (a real metric column, so compute_stability picks it up)."""
    rng = np.random.default_rng(seed)
    trait = rng.normal(80, 5, n)
    rows = []
    for s in seasons:
        for i in range(n):
            rows.append({"whoscored_player_id": i, "season": s, "league": "Premier League",
                         "total_minutes": 2000.0, "pass_accuracy_pct": trait[i] + rng.normal(0, noise)})
    return pd.DataFrame(rows)


def test_stable_metric_scores_high_and_noisy_one_low():
    seasons = ["2023-24", "2024-25", "2025-26"]
    stable = extras.compute_stability(_frame(seasons, noise=0.5))
    noisy = extras.compute_stability(_frame(seasons, noise=40.0))
    assert stable["pass_accuracy_pct"]["tier"] == "high" and stable["pass_accuracy_pct"]["r"] > 0.95
    assert noisy["pass_accuracy_pct"]["tier"] == "low"
    assert stable["pass_accuracy_pct"]["n"] == 800          # two season pairs of 400 players


def test_players_under_the_minutes_floor_and_unfinished_seasons_are_ignored():
    seasons = ["2023-24", "2024-25", "2025-26"]
    df = _frame(seasons, noise=0.5)
    df["total_minutes"] = 500.0                              # nobody clears 900 minutes
    assert "pass_accuracy_pct" not in extras.compute_stability(df)
    df = _frame(seasons + ["2026-27"], noise=0.5)
    df = df[~((df["season"] == "2026-27") & (df["whoscored_player_id"] > 50))]   # in progress: few rows
    assert extras.compute_stability(df)["pass_accuracy_pct"]["n"] == 800


def test_stale_file_is_ignored(tmp_path, monkeypatch):
    """A file built from a different table (row count differs) must never be served."""
    path = tmp_path / "extras.json"
    path.write_text(json.dumps({"rows": 3, "hub": {"facts": {"matches": 1}, "players": []},
                                "stability": {"x": {"r": 0.9, "n": 5, "tier": "high"}}, "coverage": []}))
    monkeypatch.setattr(extras, "EXTRAS_JSON", str(path))
    extras.reset()
    from core.advanced import store
    monkeypatch.setattr(store, "get_advanced_df", lambda: pd.DataFrame({"a": range(3)}))
    assert extras._file()["stability"]["x"]["tier"] == "high"           # matches: served
    monkeypatch.setattr(store, "get_advanced_df", lambda: pd.DataFrame({"a": range(4)}))
    assert extras._file() is None                                       # table changed: ignored
    extras.reset()
