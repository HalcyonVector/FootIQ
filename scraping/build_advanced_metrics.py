"""
One-time (re-runnable) ingestion script: parses all scraped WhoScored match
JSON and writes the advanced-metrics dataset under data/advanced/ —

  - player_season_advanced.parquet: per-player-season scalar/percentile
    stats, read on every /api/advanced-stats call.
  - linkup_summary.parquet: Combination Play's passer/receiver pair list
    (small, no list-columns — loaded fully into memory like the file above).
  - linkup_receptions/league=.../season=.../*.parquet: one row per reception
    event, Hive-partitioned by league+season so /api/linkup-detail reads one
    small partition on disk instead of every pair's every reception at once.
  - chart_events/<category>/league=.../season=.../*.parquet: one row per
    chart-event, same partitioning, one directory per category so
    /api/category-chart reads only the tiny slice it needs.

The partitioned layout replaces an earlier one-row-per-player-season design
where every category's events were flattened into list-columns on a single
wide row — that shape required loading every player's every event into
memory just to draw one player's chart (measured at >1GB RSS for the two
heavy files combined), which OOM-crashed on a 512MB hosting tier. Partitioned
per-event rows fix this at the data-model level: a single chart request now
reads only its own player/league/season slice, never the whole dataset.

    python scraping\\build_advanced_metrics.py
"""

import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from core.advanced import config
from core.advanced.aggregator import build_all, CHART_CATEGORIES

LEAGUES = list(config.LEAGUE_DIR_MAP.keys())
# "2022"/"2024" are World Cup 2022 and Euro 2024 — single-year competitions
# alongside the regular 3-season domestic-league cycle. build_all() tries
# every (league, season) combo and just logs "0 matches" for ones that don't
# exist (e.g. "Premier League" x "2022"), so it's safe to include both lists
# here rather than needing a per-league season map.
SEASONS = ["2023-24", "2024-25", "2025-26", "2022", "2024"]


def _write_partitioned(df: pd.DataFrame, out_dir: str) -> None:
    """Hive-partitions by league/season and rewrites the directory from
    scratch each time (safe to re-run; avoids stale partitions from leagues/
    seasons that no longer produce rows)."""
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    if df.empty:
        os.makedirs(out_dir, exist_ok=True)
        return
    df.to_parquet(out_dir, index=False, partition_cols=["league", "season"])


def main():
    t0 = time.time()
    rows, linkup_summary_rows, linkup_reception_rows, chart_rows_by_cat = build_all(LEAGUES, SEASONS)
    df = pd.DataFrame(rows)
    linkup_summary_df = pd.DataFrame(linkup_summary_rows)
    linkup_receptions_df = pd.DataFrame(linkup_reception_rows)

    os.makedirs(config.ADVANCED_DATA_DIR, exist_ok=True)
    df.to_parquet(config.PLAYER_SEASON_PARQUET, index=False)
    linkup_summary_df.to_parquet(config.LINKUP_SUMMARY_PARQUET, index=False)
    _write_partitioned(linkup_receptions_df, config.LINKUP_RECEPTIONS_DIR)

    total_chart_rows = 0
    for cat_key in CHART_CATEGORIES:
        cat_df = pd.DataFrame(chart_rows_by_cat.get(cat_key, []))
        total_chart_rows += len(cat_df)
        _write_partitioned(cat_df, os.path.join(config.CHART_EVENTS_DIR, cat_key))

    print(f"\nWrote {len(df)} player-seasons, {len(df.columns)} columns "
          f"to {config.PLAYER_SEASON_PARQUET} in {time.time()-t0:.1f}s")
    print(f"Wrote {len(linkup_summary_df)} passer-receiver pairs to {config.LINKUP_SUMMARY_PARQUET}")
    print(f"Wrote {len(linkup_receptions_df)} reception events to {config.LINKUP_RECEPTIONS_DIR}")
    print(f"Wrote {total_chart_rows} chart-event rows across {len(CHART_CATEGORIES)} categories to {config.CHART_EVENTS_DIR}")


if __name__ == "__main__":
    main()
