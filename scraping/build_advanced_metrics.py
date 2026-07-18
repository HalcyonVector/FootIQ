"""
One-time (re-runnable) ingestion script: parses all scraped WhoScored match
JSON, computes the Wave-1 advanced metrics (Passing/Shooting/Defending/
Goalkeeping), and writes data/advanced/player_season_advanced.parquet —
the only file the running Flask app reads for these stats. Mirrors the
existing fetch_understat.py / merge_understat.py one-time-script convention.

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
SEASONS = ["2023-24", "2024-25", "2025-26"]


def main():
    t0 = time.time()
    rows, linkup_rows = build_all(LEAGUES, SEASONS)
    df = pd.DataFrame(rows)
    linkup_df = pd.DataFrame(linkup_rows)

    os.makedirs(config.ADVANCED_DATA_DIR, exist_ok=True)
    df.to_parquet(config.PLAYER_SEASON_PARQUET, index=False)
    linkup_df.to_parquet(config.LINKUP_PAIRS_PARQUET, index=False)

    print(f"\nWrote {len(df)} player-seasons, {len(df.columns)} columns "
          f"to {config.PLAYER_SEASON_PARQUET} in {time.time()-t0:.1f}s")
    print(f"Wrote {len(linkup_df)} passer-receiver pairs to {config.LINKUP_PAIRS_PARQUET}")


if __name__ == "__main__":
    main()
