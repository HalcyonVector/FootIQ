"""Tests for the blocked-shot rule and the xG column merge."""
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from core.advanced.categories.shooting import is_on_target, compute_shooting
from core.advanced.xg_merge import merge_xg_columns


def test_is_on_target_rules():
    assert is_on_target("Goal", {})
    assert is_on_target("SavedShot", {})
    assert not is_on_target("SavedShot", {"Blocked": None})   # blocked by an outfielder
    assert not is_on_target("MissedShots", {})
    assert not is_on_target("ShotOnPost", {})


def _shot(typ, pid, quals):
    return {"type": typ, "player_id": pid, "x": 90.0, "y": 50.0,
            "qualifiers": [{"type": {"displayName": q}, "value": None} for q in quals]}


def test_blocked_shot_counts_as_shot_but_not_on_target():
    events = [_shot("SavedShot", 1, ["RightFoot"]),
              _shot("SavedShot", 1, ["RightFoot", "Blocked"]),
              _shot("Goal", 1, ["RightFoot"])]
    out = compute_shooting(events, [])[1]
    assert out["shots"] == 3 and out["shots_on_target"] == 2


def test_merge_xg_columns_is_idempotent_and_per90(tmp_path):
    season = tmp_path / "season.parquet"
    pd.DataFrame({"whoscored_player_id": [1, 2], "league": ["L", "L"], "season": ["s", "s"],
                  "total_minutes": [900.0, 0.0]}).to_parquet(season, index=False)
    mdir = tmp_path / "pm"
    (mdir / "league=L" / "season=s").mkdir(parents=True)
    pq.write_table(pa.table({"whoscored_player_id": [1, 1, 2], "oxg": [3.0, 2.0, 0.5],
                             "oxa": [1.0, 0.0, 0.0], "oshots": [8, 7, 1]}),
                   mdir / "league=L" / "season=s" / "a.parquet")
    assert merge_xg_columns(str(season), str(mdir)) is True
    assert merge_xg_columns(str(season), str(mdir)) is True          # re-run replaces, doesn't duplicate
    df = pd.read_parquet(season).set_index("whoscored_player_id")
    assert df.loc[1, "shoot_xg_p90"] == pytest.approx(0.5)            # 5 xG over 10 x 90'
    assert df.loc[1, "pass_xa_p90"] == pytest.approx(0.1)
    assert df.loc[1, "shoot_xg_per_shot"] == pytest.approx(5 / 15, abs=1e-3)
    assert pd.isna(df.loc[2, "shoot_xg_p90"])                          # 0 minutes -> no per-90
    assert pd.isna(df.loc[2, "shoot_xg_per_shot"])                     # < 12 shots
    assert list(df.columns).count("shoot_xg_p90") == 1


def test_merge_skips_when_overview_missing(tmp_path):
    season = tmp_path / "season.parquet"
    pd.DataFrame({"whoscored_player_id": [1]}).to_parquet(season, index=False)
    assert merge_xg_columns(str(season), str(tmp_path / "nope")) is False
