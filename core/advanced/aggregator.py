"""
Orchestrates: per-match parse -> per-category raw compute -> per-player-season
rollup -> finalized rate/percentage metrics -> per-90 conversion.

Streams one match at a time (never loads all matches' events into memory at
once) — the ~6GB raw cache is far too large for that.
"""

from collections import Counter

from core.advanced import raw_loader as rl, minutes as mn
from core.advanced.accumulate import merge_into
from core.advanced.carries import derive_carries
from core.advanced.categories import (
    passing, shooting, defending, goalkeeping,
    carrying, half_spaces, tempo, post_recovery,
    aerial, holdup, decision_making, final_third,
)
from core.advanced.linkup import compute_linkup
from core.advanced.per90 import per_90

# Categories needing only (events, rosters) — no carries/minutes.
SIMPLE_CATEGORY_MODULES = [
    (passing.compute_passing, passing.finalize_passing, passing.P90_KEYS),
    (shooting.compute_shooting, shooting.finalize_shooting, shooting.P90_KEYS),
    (defending.compute_defending, defending.finalize_defending, defending.P90_KEYS),
]
# goalkeeping (needs minutes), carrying/half_spaces/tempo/decision_making
# (need carries), post_recovery/aerial/holdup (need only events) are wired
# individually below since their compute() signatures differ.

ALL_FINALIZERS = [
    passing.finalize_passing, shooting.finalize_shooting, defending.finalize_defending,
    goalkeeping.finalize_goalkeeping, carrying.finalize_carrying, half_spaces.finalize_half_spaces,
    tempo.finalize_tempo, post_recovery.finalize_post_recovery,
    aerial.finalize_aerial, holdup.finalize_holdup, decision_making.finalize_decision_making,
    final_third.finalize_final_third,
]
ALL_P90_KEYS = (
    set(passing.P90_KEYS) | set(shooting.P90_KEYS) | set(defending.P90_KEYS) | set(goalkeeping.P90_KEYS)
    | set(carrying.P90_KEYS) | set(half_spaces.P90_KEYS) | set(tempo.P90_KEYS) | set(post_recovery.P90_KEYS)
    | set(aerial.P90_KEYS) | set(holdup.P90_KEYS) | set(decision_making.P90_KEYS) | set(final_third.P90_KEYS)
)


def build_player_season_table(league: str, season: str, collect_linkup: bool = True):
    totals: dict = {}
    meta: dict = {}  # player_id -> {name, team_name, positions: Counter, total_minutes}
    linkup_totals: dict = {}  # (passer_id, receiver_id) -> list of reception records

    n_matches = 0
    n_skipped = 0
    for fp in rl.iter_match_files(league, season):
        mj = rl.load_match_json(fp)
        if not mj or not mj.get("home") or not mj.get("away") or not mj.get("events"):
            # A handful of cached files are transient scrape failures (literal
            # JSON null, or missing events) — skip rather than crash the build.
            n_skipped += 1
            continue
        rosters = rl.parse_rosters(mj)
        events = rl.parse_events(mj)
        match_minutes = mn.compute_minutes_played(mj, events, rosters)
        n_matches += 1

        for r in rosters:
            pid = r["player_id"]
            if pid is None:
                continue
            m = meta.setdefault(pid, {
                "name": r["player_name"], "team_name": r["team_name"],
                "positions": Counter(), "total_minutes": 0.0,
            })
            m["team_name"] = r["team_name"]  # last team seen wins (mid-season transfers)
            # WhoScored tags EVERY substitute "Sub" regardless of their real
            # position (a CB coming off the bench shows "Sub", not "DC") — only
            # count starts, where the real formation slot is recorded, so a
            # part-time starter isn't misclassified by their bench appearances.
            if r["position"] and r["position"] != "Sub":
                m["positions"][r["position"]] += 1
            m["total_minutes"] += match_minutes.get(pid, 0.0)

        for compute_fn, _finalize_fn, _p90_keys in SIMPLE_CATEGORY_MODULES:
            merge_into(totals, compute_fn(events, rosters))
        merge_into(totals, goalkeeping.compute_goalkeeping(events, rosters, match_minutes))

        carries = derive_carries(events)
        merge_into(totals, carrying.compute_carrying(carries))
        merge_into(totals, carrying.compute_takeons(events))
        merge_into(totals, half_spaces.compute_half_spaces(events, carries))
        merge_into(totals, tempo.compute_tempo(events, carries))
        merge_into(totals, post_recovery.compute_post_recovery(events))
        merge_into(totals, aerial.compute_aerial(events))
        merge_into(totals, holdup.compute_holdup(events))
        merge_into(totals, decision_making.compute_decision_making(events, carries))
        merge_into(totals, final_third.compute_final_third(events, carries))

        if collect_linkup:
            for pair, receptions in compute_linkup(events).items():
                linkup_totals.setdefault(pair, []).extend(receptions)

    rows = []
    finalized_by_category = [finalize_fn(totals) for finalize_fn in ALL_FINALIZERS]

    for pid, m in meta.items():
        total_min = m["total_minutes"]
        row = {
            "whoscored_player_id": pid,
            "player_name": m["name"],
            "team_name": m["team_name"],
            "league": league,
            "season": season,
            "position": m["positions"].most_common(1)[0][0] if m["positions"] else None,
            "total_minutes": round(total_min, 1),
        }
        for cat_final in finalized_by_category:
            player_fields = cat_final.get(pid, {})
            for k, v in player_fields.items():
                if k in ALL_P90_KEYS:
                    row[f"{k}_p90"] = round(per_90(v, int(total_min)), 3) if total_min >= 1 else None
                else:
                    row[k] = v
        rows.append(row)

    linkup_rows = []
    for (passer_id, receiver_id), receptions in linkup_totals.items():
        passer_meta = meta.get(passer_id)
        receiver_meta = meta.get(receiver_id)
        if not passer_meta or not receiver_meta:
            continue
        linkup_rows.append({
            "passer_id": passer_id, "receiver_id": receiver_id,
            "passer_name": passer_meta["name"], "receiver_name": receiver_meta["name"],
            "team_name": passer_meta["team_name"],
            "league": league, "season": season,
            "count": len(receptions),
            "reception_x": [r["reception_x"] for r in receptions],
            "reception_y": [r["reception_y"] for r in receptions],
            "outcome": [r["outcome"] for r in receptions],
            "end_x": [r["end_x"] for r in receptions],
            "end_y": [r["end_y"] for r in receptions],
        })

    skip_note = f", {n_skipped} skipped (corrupted)" if n_skipped else ""
    print(f"[advanced] {league} {season}: {n_matches} matches{skip_note}, {len(rows)} player-seasons, {len(linkup_rows)} linkup pairs")
    return rows, linkup_rows


def build_all(leagues: list[str], seasons: list[str]):
    all_rows, all_linkup_rows = [], []
    for league in leagues:
        for season in seasons:
            rows, linkup_rows = build_player_season_table(league, season)
            all_rows.extend(rows)
            all_linkup_rows.extend(linkup_rows)
    return all_rows, all_linkup_rows
