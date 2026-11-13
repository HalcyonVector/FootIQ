"""
Data health check: scans the raw WhoScored cache for every (league, season)
combo and reports how many cached matches are unusable — literal null JSON,
or unreadable/corrupted — per the exact symptom that revealed Conference
League's coverage gap (100% null, discovered by hand). Run this after any
scrape to catch that kind of gap automatically instead of by accident.

    python scraping/check_data_health.py
    python scraping/check_data_health.py --threshold 0.10

Exits 1 if anything is flagged, 0 otherwise — safe to wire into a CI step
or just run manually after a scrape.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.advanced import config
from core.advanced.raw_loader import iter_match_files, load_match_json

DEFAULT_NULL_RATE_WARN = 0.05  # flag any league-season with >5% unusable matches
ALL_SEASONS = config.all_domestic_seasons() + ["2022", "2024"]


def check_league_seasons(threshold: float, leagues=None, seasons=None, current=None) -> list[dict]:
    """For the season being played right now a literal-null file is a fixture that has
    not happened yet (the cache holds a placeholder for every scheduled match), so
    those are counted as `pending`, not unusable. Only unreadable files count against
    the current season; a finished season has no pending fixtures, so there every
    null file is a real gap."""
    leagues = leagues or list(config.LEAGUE_DIR_MAP.keys())
    seasons = seasons or ALL_SEASONS
    current = current if current is not None else config.current_season()
    results = []
    for league in leagues:
        for season in seasons:
            files = list(iter_match_files(league, season))
            if not files:
                continue  # this (league, season) combo was never scraped — not a health issue, just absent
            bad = pending = 0
            for fp in files:
                try:
                    if load_match_json(fp) is None:
                        if season == current:
                            pending += 1
                        else:
                            bad += 1
                except Exception:
                    bad += 1
            total = len(files) - pending        # fixtures still to be played are not part of the sample
            if total <= 0:
                continue
            rate = bad / total
            results.append({
                "league": league, "season": season, "total": total, "pending": pending,
                "bad": bad, "rate": rate, "flagged": rate > threshold,
            })
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=DEFAULT_NULL_RATE_WARN,
                         help=f"Flag any league-season above this unusable-match rate (default {DEFAULT_NULL_RATE_WARN})")
    args = parser.parse_args()

    results = check_league_seasons(args.threshold)
    if not results:
        print("No cached matches found at all — check FOOTIQ_WHOSCORED_DIR / WHOSCORED_CACHE_DIR.")
        sys.exit(1)

    print(f"{'League':<28} {'Season':<10} {'Matches':>8} {'Unusable':>9} {'Rate':>8} {'Not played yet':>15}")
    print("-" * 84)
    for r in sorted(results, key=lambda r: -r["rate"]):
        marker = "  <-- FLAGGED" if r["flagged"] else ""
        print(f"{r['league']:<28} {r['season']:<10} {r['total']:>8} {r['bad']:>9} {r['rate']*100:>7.1f}% {r['pending']:>14}{marker}")

    flagged = [r for r in results if r["flagged"]]
    print()
    if flagged:
        print(f"FLAGGED: {len(flagged)} league-season(s) above {args.threshold*100:.0f}% unusable:")
        for r in flagged:
            print(f"  - {r['league']} {r['season']}: {r['bad']}/{r['total']} unusable ({r['rate']*100:.1f}%)")
        sys.exit(1)

    print("All league-seasons within acceptable range.")
    sys.exit(0)


if __name__ == "__main__":
    main()
