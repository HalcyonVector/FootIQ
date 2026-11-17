"""
One-off repair of data/advanced/player_season_advanced.parquet: recompute `season_progress` for the
European cups from the number of matches parsed, without the 75-minute full rebuild.

Until the gates change, the aggregator wrote 1.0 ("finished") for every cup, so a Champions League or
Europa League season that is half played was listed as Finished with nobody above the minutes floor.
The next full rebuild (build_advanced_metrics.py, which the weekly update runs) writes the right value
itself; this applies the same rule to the data that is already built:

    python scraping/patch_cup_progress.py
    python scraping/build_extras.py          # refresh the coverage table

Only the progress column (and so the minutes floor) changes. The sample-size gates on ratio metrics
inside those seasons were applied at build time and are refreshed by the next full rebuild.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def main() -> None:
    import pandas as pd
    from core.advanced import config, gates, store

    df = pd.read_parquet(config.PLAYER_SEASON_PARQUET)
    ds = store._overview_dataset("matches", config.PLAYER_MATCHES_DIR)
    t = ds.to_table(columns=["league", "season", "match_key"]).to_pandas().drop_duplicates()
    matches = t.groupby(["league", "season"])["match_key"].nunique().to_dict()

    changed = 0
    for (league, season), n in matches.items():
        if league not in gates.CUP_EDITION_MATCHES:
            continue
        new = gates.season_progress(league, int(n), 0, season)
        mask = (df["league"] == league) & (df["season"] == season)
        if not mask.any():
            continue
        old = df.loc[mask, "season_progress"].iloc[0]
        if abs(float(old) - new) > 1e-9:
            df.loc[mask, "season_progress"] = new
            changed += int(mask.sum())
            print(f"{league} {season}: {n} matches, progress {old} -> {new}")
    if changed:
        df.to_parquet(config.PLAYER_SEASON_PARQUET, index=False)
    print(f"{changed} rows updated")


if __name__ == "__main__":
    main()
