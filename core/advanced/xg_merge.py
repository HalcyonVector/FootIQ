"""
Folds expected-goals stats into player_season_advanced.parquet so they behave
like every other metric (percentile-ranked in the tabs, usable in Compare,
Scout and Explore).

Source is the Season Overview's per-match table (player_matches/, built by
scraping/build_overview_data.py), summed per player-season. Open-play only,
matching the Shooting and Passing tabs' own "open play only" rule:

  shoot_xg_p90        open-play xG per 90
  shoot_xg_per_shot   open-play xG / open-play shots (>= 12 shots, like Conversion)
  pass_xa_p90         open-play xA per 90 (xG of shots a player's open-play pass set up)

Idempotent: re-running replaces these columns. Both build scripts call it
last, so it works whichever order they run in -- and it quietly does nothing
if the overview data hasn't been built yet.
"""

import os

import math

import pandas as pd
import pyarrow.dataset as pa_ds

from core.advanced import config

XG_COLUMNS = ["shoot_xg_p90", "shoot_xg_per_shot", "pass_xa_p90"]
MIN_SHOTS_FOR_PER_SHOT = 12


def merge_xg_columns(season_parquet: str = config.PLAYER_SEASON_PARQUET,
                     matches_dir: str = config.PLAYER_MATCHES_DIR) -> bool:
    if not (os.path.exists(season_parquet) and os.path.isdir(matches_dir)):
        print("[xg_merge] no season parquet or overview data yet -- skipped")
        return False
    ds = pa_ds.dataset(matches_dir, format="parquet", partitioning="hive")
    needed = ["oxg", "oxa", "oshots"]
    if any(c not in ds.schema.names for c in needed):
        print("[xg_merge] overview data predates open-play xG columns -- skipped (rebuild it)")
        return False

    pm = ds.to_table(columns=["whoscored_player_id", "league", "season", *needed]).to_pandas()
    agg = pm.groupby(["whoscored_player_id", "league", "season"], as_index=False)[needed].sum()

    df = pd.read_parquet(season_parquet)
    df = df.drop(columns=[c for c in XG_COLUMNS if c in df.columns])
    df = df.merge(agg, on=["whoscored_player_id", "league", "season"], how="left")

    mins = df["total_minutes"].where(df["total_minutes"] >= 1)
    df["shoot_xg_p90"] = (df["oxg"] / mins * 90).round(3)
    df["pass_xa_p90"] = (df["oxa"] / mins * 90).round(3)
    # same in-progress-season relaxation as core/advanced/gates.py, applied per row
    progress = df["season_progress"].fillna(1.0).clip(0, 1) if "season_progress" in df.columns else 1.0
    need = (MIN_SHOTS_FOR_PER_SHOT * progress).apply(lambda v: max(min(MIN_SHOTS_FOR_PER_SHOT, 3), math.ceil(v))) \
        if hasattr(progress, "apply") else MIN_SHOTS_FOR_PER_SHOT
    df["shoot_xg_per_shot"] = (df["oxg"] / df["oshots"].where(df["oshots"] >= need)).round(3)
    df = df.drop(columns=needed)
    df.to_parquet(season_parquet, index=False)
    print(f"[xg_merge] added {', '.join(XG_COLUMNS)} to {len(df)} player-seasons")
    return True
