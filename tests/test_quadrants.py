"""Quadrant plots: every preset points at real columns, and the 0-100 index behaves."""
from pathlib import Path

import pandas as pd
import pytest

from core.advanced import quadrants
from core.advanced.explore import explorable_metrics
from visuals import specs

DATA = Path(__file__).resolve().parent.parent / "data" / "advanced" / "player_season_advanced.parquet"


def _df():
    rows = []
    for i in range(6):
        rows.append({"whoscored_player_id": i, "player_name": f"P{i}", "team_name": "T", "league": "La Liga",
                     "season": "2025-26", "_pos_group": "midfielder" if i < 5 else "goalkeeper",
                     "total_minutes": 2000, "ax": float(i), "ay": float(5 - i), "az": float(i)})
    return pd.DataFrame(rows)


@pytest.fixture
def tiny(monkeypatch):
    preset = {"id": "t", "title": "t", "positions": "midfielder", "question": "q",
              "x": {"label": "X", "cols": ["ax", "az"]}, "y": {"label": "Y", "cols": ["ay"]},
              "quad": {"tr": "a", "tl": "b", "br": "c", "bl": "d"}}
    monkeypatch.setitem(quadrants.BY_ID, "t", preset)
    return preset


def test_index_is_mean_percentile_and_goalkeepers_stay_out(tiny):
    res = quadrants.quadrant_points(_df(), "t", "2025-26", "all", "all", 450)
    pts = {p["name"]: p for p in res["points"]}
    assert set(pts) == {"P0", "P1", "P2", "P3", "P4"}                    # the keeper is not a midfielder
    assert pts["P4"]["x"] > pts["P0"]["x"] and pts["P4"]["y"] < pts["P0"]["y"]
    assert 0 < min(p["x"] for p in pts.values()) and max(p["x"] for p in pts.values()) == 100
    assert pts["P0"]["raw"] == [0.0, 0.0, 5.0]                           # x parts then y parts, for the tooltip


def test_position_filter_overrides_the_default_group(tiny):
    res = quadrants.quadrant_points(_df(), "t", "2025-26", "all", "goalkeeper", 450)
    assert [p["name"] for p in res["points"]] == ["P5"]


def test_spec_carries_corner_names_and_parts(tiny):
    res = quadrants.quadrant_points(_df(), "t", "2025-26", "all", "all", 450)
    spec = specs.quadrant_plot(res, {"ax": {"label": "Ax", "unit": ""}})
    assert spec["quad"]["tr"] == "a" and spec["xparts"][0][0] == "Ax" and len(spec["points"][0]) == 10


def test_presets_are_well_formed():
    assert len({p["id"] for p in quadrants.PRESETS}) == len(quadrants.PRESETS)
    for p in quadrants.PRESETS:
        assert set(p["quad"]) == {"tr", "tl", "br", "bl"}
        assert p["positions"] in {"attacker", "attacking", "midfielder", "defender", "goalkeeper"}


def test_every_preset_uses_labelled_columns():
    labelled = {m["col"] for c in explorable_metrics() for m in c["metrics"]} | set(quadrants.EXTRA_LABELS)
    for p in quadrants.PRESETS:
        for col in p["x"]["cols"] + p["y"]["cols"]:
            assert col in labelled, (p["id"], col)


@pytest.mark.skipif(not DATA.exists(), reason="data release not downloaded")
def test_every_preset_has_players_in_the_real_data():
    df = pd.read_parquet(DATA)
    from core.position import pos_group
    df["_pos_group"] = df["position"].map(lambda v: pos_group(v))
    season = sorted(df["season"].unique())[-2]                          # a finished season
    for p in quadrants.PRESETS:
        res = quadrants.quadrant_points(df, p["id"], season, "all", "all", 450)
        assert len(res["points"]) >= 30, (p["id"], len(res["points"]))
