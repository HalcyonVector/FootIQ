"""Explore's scatter points obey the same filters as the ranked list."""
import pandas as pd

from core.advanced import explore


def _df():
    rows = []
    for i, (lg, grp, mins, x, y) in enumerate([
        ("Premier League", "midfielder", 2000, 1.0, 2.0), ("Premier League", "defender", 2500, 3.0, 4.0),
        ("La Liga", "midfielder", 1800, 5.0, 6.0), ("La Liga", "midfielder", 100, 7.0, 8.0),
        ("La Liga", "midfielder", 2200, 9.0, None),
    ]):
        rows.append({"whoscored_player_id": i, "player_name": f"P{i}", "team_name": "T", "league": lg, "season": "2025-26",
                     "_pos_group": grp, "total_minutes": mins, "position": "MC", "age": 25, "mx": x, "my": y})
    return pd.DataFrame(rows)


def test_filters_minutes_and_missing_values():
    pts = explore.scatter_points(_df(), "mx", "my", "2025-26", "all", "all", 450)
    assert sorted(p["name"] for p in pts) == ["P0", "P1", "P2"]          # P3 under the floor, P4 has no y


def test_league_and_position_filters_and_ordering():
    pts = explore.scatter_points(_df(), "mx", "my", "2025-26", "La Liga", "midfielder", 450)
    assert [p["name"] for p in pts] == ["P2"]
    allp = explore.scatter_points(_df(), "mx", "my", "2025-26", "all", "all", 450, limit=2)
    assert [p["name"] for p in allp] == ["P1", "P0"]                    # kept the two with most minutes


def test_unknown_metric_gives_nothing():
    assert explore.scatter_points(_df(), "mx", "nope", "2025-26") == []
