"""
One-off verification script: confirms WhoScored/Opta event coordinates are
attack-direction-normalized per event (x=0 own goal, x=100 opponent goal),
not raw pitch-fixed. If they were pitch-fixed, a team's Goal events would
cluster near x=100 in the half where they attack that end and near x=0 in
the other half. Run this once; if it prints "NORMALIZED", geometry.py's
assumptions hold across all 5 leagues.

    python -m core.advanced.verify_coordinates
"""

import random

from core.advanced import config, qualifiers as q, raw_loader as rl


def run(n_matches_per_league: int = 60):
    all_goal_x = []
    own_goal_x = []
    samples_by_league = {}

    for league in config.LEAGUE_DIR_MAP:
        files = []
        for season in ("2023-24", "2024-25", "2025-26"):
            files.extend(rl.iter_match_files(league, season))
        if not files:
            continue
        sample = random.sample(files, min(n_matches_per_league, len(files)))
        league_goal_x = []

        for fp in sample:
            mj = rl.load_match_json(fp)
            events = rl.parse_events(mj)
            for e in events:
                if e["type"] == "Goal":
                    qm = q.qmap(e["qualifiers"])
                    x = e["x"]
                    if x is None:
                        continue
                    if q.has_qualifier(qm, q.OWN_GOAL_Q):
                        own_goal_x.append(x)
                    else:
                        league_goal_x.append(x)
                        all_goal_x.append(x)

        samples_by_league[league] = league_goal_x

    print(f"Sampled goal-event x across {sum(len(v) for v in samples_by_league.values())} regular goals, "
          f"{len(own_goal_x)} own goals\n")
    for league, xs in samples_by_league.items():
        if not xs:
            print(f"  {league}: no goals sampled")
            continue
        avg = sum(xs) / len(xs)
        lo, hi = min(xs), max(xs)
        print(f"  {league}: n={len(xs):4d}  mean_x={avg:6.2f}  range=[{lo:.1f}, {hi:.1f}]")

    if all_goal_x:
        overall_avg = sum(all_goal_x) / len(all_goal_x)
        print(f"\nOverall regular-goal mean x: {overall_avg:.2f} (expect ~85-100 if normalized)")
        if own_goal_x:
            og_avg = sum(own_goal_x) / len(own_goal_x)
            print(f"Own-goal mean x: {og_avg:.2f} (expect ~0-15 if normalized, since it's in the SCORING team's frame)")
        verdict = "NORMALIZED" if overall_avg > 75 else "NOT NORMALIZED / MIXED — investigate before trusting geometry.py"
        print(f"\nVERDICT: {verdict}")


if __name__ == "__main__":
    run()
