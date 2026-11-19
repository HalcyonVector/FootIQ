"""
Builds data/advanced/extras.json: the home page facts, the featured players' radar numbers, the
season-to-season reliability of each metric and the coverage table (see core/advanced/extras.py).

Run after build_advanced_metrics.py and build_overview_data.py, before publishing the data:

    python scraping/build_extras.py

It takes a couple of seconds. The app falls back to computing the same figures on demand if the
file is missing or was built from a different player-season table, so it is purely a speed-up.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def missing_matches() -> dict:
    """{(league, season): (matches with no event data, matches in the cache)} for finished seasons.

    The cache holds a file per scheduled match, and a match the source has no events for is a literal
    `null`. Such files are a few bytes, so only tiny files are opened. The season being played is
    skipped: there a `null` is a fixture not played yet (see check_data_health.py)."""
    from core.advanced import config
    from core.advanced.raw_loader import iter_match_files
    current = config.current_season()
    out = {}
    for league in config.LEAGUE_DIR_MAP:
        for season in config.all_domestic_seasons() + ["2022", "2024"]:
            if season == current:
                continue
            n = nulls = 0
            for fp in iter_match_files(league, season):
                n += 1
                try:
                    if fp.stat().st_size <= 16 and fp.read_text(encoding="utf-8").strip() in ("null", ""):
                        nulls += 1
                except OSError:
                    nulls += 1
            if n:
                out[(league, season)] = (nulls, n)
    return out


def main() -> None:
    import json
    from core.advanced import extras, lookup, store
    t0 = time.time()
    df = store.get_advanced_df()
    lookup.build_search_index()
    out = extras.build(df)
    # Matches the source has no events for, per competition-season (needs the raw cache, so it is only
    # added where the data is built; the app treats a missing field as "none known").
    try:
        missing = missing_matches()
    except Exception as e:
        missing = {}
        print(f"(could not count missing matches: {e})")
    for row in out["coverage"]:
        nulls, n = missing.get((row["league"], row["season"]), (0, 0))
        row["missing"], row["scheduled"] = nulls, n
    # How each team plays, per competition-season (core/advanced/teams.py)
    from core.advanced import teams
    out["teams"] = teams.build_all([(r["league"], r["season"]) for r in out["coverage"]])
    with open(extras.EXTRAS_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"))
    f = out["hub"]["facts"]
    print(f"Wrote {extras.EXTRAS_JSON} in {time.time() - t0:.1f}s: {f['matches']} matches, {f['players']} players, "
          f"{len(out['hub']['players'])} featured, {len(out['stability'])} metric stabilities, {len(out['coverage'])} coverage rows")


if __name__ == "__main__":
    main()
