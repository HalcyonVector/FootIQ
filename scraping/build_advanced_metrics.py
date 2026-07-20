"""
One-time (re-runnable) ingestion script: parses all scraped WhoScored match
JSON and writes three parquet files under data/advanced/ —
player_season_advanced.parquet (per-player-season scalar/percentile stats,
read on every /api/advanced-stats call), linkup_pairs.parquet (Combination
Play's pairwise reception data), and player_chart_events.parquet (raw
per-category event coordinates behind the per-tab charts, loaded lazily
only when a chart is requested).

    python scraping\\build_advanced_metrics.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from core.advanced import config
from core.advanced.aggregator import build_all

LEAGUES = list(config.LEAGUE_DIR_MAP.keys())
# "2022"/"2024" are World Cup 2022 and Euro 2024 — single-year competitions
# alongside the regular 3-season domestic-league cycle. build_all() tries
# every (league, season) combo and just logs "0 matches" for ones that don't
# exist (e.g. "Premier League" x "2022"), so it's safe to include both lists
# here rather than needing a per-league season map.
SEASONS = ["2023-24", "2024-25", "2025-26", "2022", "2024"]


def main():
    t0 = time.time()
    rows, linkup_rows, chart_rows = build_all(LEAGUES, SEASONS)
    df = pd.DataFrame(rows)
    linkup_df = pd.DataFrame(linkup_rows)
    chart_df = pd.DataFrame(chart_rows)

    os.makedirs(config.ADVANCED_DATA_DIR, exist_ok=True)
    df.to_parquet(config.PLAYER_SEASON_PARQUET, index=False)
    linkup_df.to_parquet(config.LINKUP_PAIRS_PARQUET, index=False)
    chart_df.to_parquet(config.CHART_EVENTS_PARQUET, index=False)

    print(f"\nWrote {len(df)} player-seasons, {len(df.columns)} columns "
          f"to {config.PLAYER_SEASON_PARQUET} in {time.time()-t0:.1f}s")
    print(f"Wrote {len(linkup_df)} passer-receiver pairs to {config.LINKUP_PAIRS_PARQUET}")
    print(f"Wrote {len(chart_df)} chart-event rows, {len(chart_df.columns)} columns to {config.CHART_EVENTS_PARQUET}")


if __name__ == "__main__":
    main()
