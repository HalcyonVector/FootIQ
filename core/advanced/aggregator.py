"""
Orchestrates: per-match parse -> per-category raw compute -> per-player-season
rollup -> finalized rate/percentage metrics -> per-90 conversion.

Streams one match at a time (never loads all matches' events into memory at
once) — the ~6GB raw cache is far too large for that.
"""

from collections import Counter

from core.advanced import raw_loader as rl, minutes as mn, chart_events as ce
from core.advanced.accumulate import merge_into
from core.advanced.carries import derive_carries
from core.advanced.categories import (
    passing, shooting, defending, goalkeeping,
    carrying, half_spaces, tempo, post_recovery,
    aerial, holdup, decision_making, final_third,
)
from core.advanced.linkup import compute_linkup
from core.advanced.per90 import per_90

# Wave 5: per-category chart-event fields, flattened into parallel list-columns
# (evt_<category>_<field>) in data/advanced/player_chart_events.parquet — the
# same shape linkup_pairs.parquet already proved out. A fixed field tuple per
# category (rather than inferring from dict keys) keeps the parquet schema
# stable even for a player-season with zero records in some category.
CHART_FIELDS = {
    "passing": ("x", "y", "end_x", "end_y", "completed", "progressive", "into_box", "release_s"),
    "shooting": ("x", "y", "outcome", "body_part"),
    "carrying": ("start_x", "start_y", "end_x", "end_y", "progressive", "followup"),
    "takeons": ("x", "y", "outcome"),
    "aerial": ("x", "y", "won", "phase"),
    "holdup": ("x", "y", "zone", "outcome"),
    "half_space_off": ("x", "y", "end_x", "end_y", "kind"),
    "half_space_def": ("x", "y", "kind"),
    "tempo": ("x", "y", "end_x", "end_y", "kind", "release_s"),
    "defending": ("x", "y", "action", "outcome"),
    "post_recovery": ("x", "y", "end_x", "end_y", "outcome"),
    "goalkeeping": ("x", "y", "outcome"),
}


def _merge_chart_events(chart_totals: dict, category: str, records_by_pid: dict) -> None:
    for pid, records in records_by_pid.items():
        chart_totals.setdefault(pid, {}).setdefault(category, []).extend(records)


def _flatten_chart_records(prefix: str, records: list, fields: tuple) -> dict:
    return {f"evt_{prefix}_{field}": [r.get(field) for r in records] for field in fields}

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


def build_player_season_table(league: str, season: str, collect_linkup: bool = True, collect_chart_events: bool = True):
    totals: dict = {}
    meta: dict = {}  # player_id -> {name, team_name, positions: Counter, total_minutes}
    linkup_totals: dict = {}  # (passer_id, receiver_id) -> list of reception records
    chart_totals: dict = {}  # player_id -> {category: [event records]}

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
                "positions": Counter(), "total_minutes": 0.0, "age": None,
            })
            m["team_name"] = r["team_name"]  # last team seen wins (mid-season transfers)
            if r.get("age"):
                m["age"] = r["age"]  # last match seen wins -> age as of their most recent appearance
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

        if collect_chart_events:
            _merge_chart_events(chart_totals, "passing", ce.extract_passing(events))
            _merge_chart_events(chart_totals, "shooting", ce.extract_shooting(events))
            _merge_chart_events(chart_totals, "carrying", ce.extract_carrying(events))
            _merge_chart_events(chart_totals, "takeons", ce.extract_takeons(events))
            _merge_chart_events(chart_totals, "aerial", ce.extract_aerial(events))
            _merge_chart_events(chart_totals, "holdup", ce.extract_holdup(events))
            hs_off, hs_def = ce.extract_half_spaces(events, carries)
            _merge_chart_events(chart_totals, "half_space_off", hs_off)
            _merge_chart_events(chart_totals, "half_space_def", hs_def)
            _merge_chart_events(chart_totals, "tempo", ce.extract_tempo(events, carries))
            _merge_chart_events(chart_totals, "defending", ce.extract_defending(events))
            _merge_chart_events(chart_totals, "post_recovery", ce.extract_post_recovery(events))
            _merge_chart_events(chart_totals, "goalkeeping", ce.extract_goalkeeping(events, rosters, match_minutes))

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
            "age": m["age"],
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

    chart_rows = []
    for pid, cats in chart_totals.items():
        m = meta.get(pid)
        if not m:
            continue
        row = {"whoscored_player_id": pid, "league": league, "season": season}
        for cat_key, fields in CHART_FIELDS.items():
            row.update(_flatten_chart_records(cat_key, cats.get(cat_key, []), fields))
        chart_rows.append(row)

    skip_note = f", {n_skipped} skipped (corrupted)" if n_skipped else ""
    print(f"[advanced] {league} {season}: {n_matches} matches{skip_note}, {len(rows)} player-seasons, "
          f"{len(linkup_rows)} linkup pairs, {len(chart_rows)} chart-event rows")
    return rows, linkup_rows, chart_rows


def build_all(leagues: list[str], seasons: list[str]):
    all_rows, all_linkup_rows, all_chart_rows = [], [], []
    for league in leagues:
        for season in seasons:
            rows, linkup_rows, chart_rows = build_player_season_table(league, season)
            all_rows.extend(rows)
            all_linkup_rows.extend(linkup_rows)
            all_chart_rows.extend(chart_rows)
    return all_rows, all_linkup_rows, all_chart_rows
