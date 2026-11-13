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


def main() -> None:
    from core.advanced import extras, lookup, store
    t0 = time.time()
    df = store.get_advanced_df()
    lookup.build_search_index()
    out = extras.build(df)
    f = out["hub"]["facts"]
    print(f"Wrote {extras.EXTRAS_JSON} in {time.time() - t0:.1f}s: {f['matches']} matches, {f['players']} players, "
          f"{len(out['hub']['players'])} featured, {len(out['stability'])} metric stabilities, {len(out['coverage'])} coverage rows")


if __name__ == "__main__":
    main()
