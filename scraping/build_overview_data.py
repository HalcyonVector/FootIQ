"""
Builds the player "Overview" datasets (stat line, form chart, shot map, xG,
heatmaps) from the raw WhoScored match JSON. Separate from
build_advanced_metrics.py on purpose: it never touches the percentile
parquet, so Compare / Scout / Explore are unaffected, and it can be re-run
on its own.

Writes under data/advanced/:
  player_matches/league=/season=/   one row per player per match played
  shots/league=/season=/            one row per shot, with xG
  heatmaps/league=/season=/         per player-season touch + defensive grids
  xg_model.json                     fitted xG coefficients (tiny)

    python scraping\\build_overview_data.py

Subset for testing (writes elsewhere so real data isn't clobbered):
    python scraping\\build_overview_data.py --leagues "Premier League" --seasons 2024-25 --out-dir D:\\tmp\\ov
"""

import argparse
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from core.advanced import config, minutes as mn, raw_loader as rl, xg
from core.advanced.overview import GRID_X, GRID_Y, extract_match
from core.advanced.partition_io import write_partitioned

ALL_LEAGUES = list(config.LEAGUE_DIR_MAP.keys())
ALL_SEASONS = config.all_domestic_seasons() + ["2022", "2024"]

SHOT_OUT_COLS = ["whoscored_player_id", "assist_pid", "ax", "ay", "aex", "aey", "minute", "x", "y",
                 "outcome", "situation", "body", "big_chance", "gm_y", "gm_z", "xg", "league", "season"]


def _features(shots: pd.DataFrame) -> np.ndarray:
    return np.array([
        xg.feature_vector(r.x, r.y, {
            "head": r.f_head, "big_chance": r.big_chance, "direct_fk": r.f_direct_fk,
            "corner": r.f_corner, "other_set_piece": r.f_other_sp, "fast_break": r.f_fast_break,
            "assisted": r.f_assisted, "other_body_part": r.f_other_body,
        }) for r in shots.itertuples(index=False)
    ])


def _write_partitioned(df_or_table, out_dir: str) -> None:
    """Atomic swap + unchanged partitions keep their old bytes (so the
    release zip hashes the same when nothing changed) -- see core/advanced/partition_io.py."""
    write_partitioned(df_or_table, out_dir, compression="zstd")


def _scan(leagues, seasons):
    pm_parts, shot_parts, heat_parts = [], [], []
    for league in leagues:
        for season in seasons:
            t0 = time.time()
            rows, shots = [], []
            heat_tot: dict = {}
            n = 0
            for fp in rl.iter_match_files(league, season):
                mj = rl.load_match_json(fp)
                if not mj or not mj.get("home") or not mj.get("away") or not mj.get("events"):
                    continue
                events = rl.parse_events(mj)
                rosters = rl.parse_rosters(mj)
                mins = mn.compute_minutes_played(mj, events, rosters)
                pr, sr, heat = extract_match(fp.stem, mj, events, mins)
                rows += pr
                shots += sr
                for pid, (t, d) in heat.items():
                    cur = heat_tot.get(pid)
                    if cur is None:
                        heat_tot[pid] = [t.astype(np.uint32), d.astype(np.uint32)]
                    else:
                        cur[0] += t
                        cur[1] += d
                n += 1
            if not n:
                continue
            pm = pd.DataFrame(rows)
            pm["league"], pm["season"] = league, season
            pm_parts.append(pm)
            sh = pd.DataFrame(shots)
            if not sh.empty:
                sh["league"], sh["season"] = league, season
                shot_parts.append(sh)
            heat_parts.append(pd.DataFrame({
                "whoscored_player_id": list(heat_tot.keys()),
                "touches": [np.minimum(v[0], 65535).astype(np.uint16) for v in heat_tot.values()],
                "defs": [np.minimum(v[1], 65535).astype(np.uint16) for v in heat_tot.values()],
                "league": league, "season": season,
            }))
            print(f"[overview] {league} {season}: {n} matches, {len(pm)} player-matches, "
                  f"{len(sh)} shots ({time.time()-t0:.0f}s)", flush=True)
    return pm_parts, shot_parts, heat_parts


def _fit_xg(shots: pd.DataFrame) -> dict:
    pens = shots[shots.situation == "penalty"]
    pen_rate = float((pens.outcome == "goal").mean()) if len(pens) else 0.76
    open_ = shots[shots.situation != "penalty"]
    X = _features(open_)
    y = (open_.outcome == "goal").to_numpy(dtype=float)
    model = xg.fit(X, y, pen_rate)
    p = xg.predict(model, X)
    ll = float(-np.mean(y * np.log(p + 1e-12) + (1 - y) * np.log(1 - p + 1e-12)))
    base = y.mean()
    ll0 = float(-np.mean(y * np.log(base) + (1 - y) * np.log(1 - base)))
    # AUC via the rank-sum statistic
    order = p.argsort()
    ranks = np.empty(len(p))
    ranks[order] = np.arange(1, len(p) + 1)
    n1 = y.sum()
    n0 = len(y) - n1
    auc = float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))
    print(f"[xg] {len(open_)} shots, {int(y.sum())} goals, penalty rate {pen_rate:.3f} ({len(pens)} pens)")
    print(f"[xg] total xG {p.sum():.0f} vs goals {int(y.sum())}; logloss {ll:.4f} (baseline {ll0:.4f}); AUC {auc:.3f}")
    return model


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", nargs="*", default=ALL_LEAGUES)
    ap.add_argument("--seasons", nargs="*", default=ALL_SEASONS)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()
    subset = set(args.leagues) != set(ALL_LEAGUES) or set(args.seasons) != set(ALL_SEASONS)
    if subset and not args.out_dir:
        ap.error("a subset build needs --out-dir so it doesn't overwrite the full dataset")
    out = args.out_dir or config.ADVANCED_DATA_DIR
    os.makedirs(out, exist_ok=True)

    t0 = time.time()
    pm_parts, shot_parts, heat_parts = _scan(args.leagues, args.seasons)
    pm = pd.concat(pm_parts, ignore_index=True)
    shots = pd.concat(shot_parts, ignore_index=True)
    heat = pd.concat(heat_parts, ignore_index=True)

    model = _fit_xg(shots)
    xg.save(model, os.path.join(out, "xg_model.json"))

    # xG per shot (penalties flat), then roll up to player-match: own xG,
    # non-penalty xG, and xA (xG of shots this player's pass set up).
    is_pen = (shots.situation == "penalty").to_numpy()
    shots["xg"] = np.where(is_pen, model["penalty_xg"], xg.predict(model, _features(shots)))
    shots["xg"] = shots["xg"].round(3)
    own = shots.groupby(["match_key", "whoscored_player_id"]).agg(xg=("xg", "sum")).reset_index()
    npx = shots[~is_pen].groupby(["match_key", "whoscored_player_id"]).agg(npxg=("xg", "sum")).reset_index()
    xa = (shots[shots.assist_pid.notna() & ~is_pen]
          .groupby(["match_key", "assist_pid"]).agg(xa=("xg", "sum")).reset_index()
          .rename(columns={"assist_pid": "whoscored_player_id"}))
    xa["whoscored_player_id"] = xa["whoscored_player_id"].astype("int64")
    # Open-play-only versions (the Shooting / Passing tabs are open play only):
    # own xG + shot count, and xA from open-play shots.
    is_open = (shots.situation == "open_play").to_numpy()
    oown = (shots[is_open].groupby(["match_key", "whoscored_player_id"])
            .agg(oxg=("xg", "sum"), oshots=("xg", "size")).reset_index())
    oxa = (shots[is_open & shots.assist_pid.notna().to_numpy()]
           .groupby(["match_key", "assist_pid"]).agg(oxa=("xg", "sum")).reset_index()
           .rename(columns={"assist_pid": "whoscored_player_id"}))
    oxa["whoscored_player_id"] = oxa["whoscored_player_id"].astype("int64")
    for extra in (own, npx, xa, oown, oxa):
        pm = pm.merge(extra, on=["match_key", "whoscored_player_id"], how="left")
    for c in ("xg", "npxg", "xa", "oxg", "oxa"):
        pm[c] = pm[c].fillna(0.0).round(3)
    pm["oshots"] = pm["oshots"].fillna(0).astype("int32")
    pm = pm.sort_values(["league", "season", "date"], kind="stable")

    _write_partitioned(pm, os.path.join(out, "player_matches"))
    shots_out = shots[SHOT_OUT_COLS].copy()
    shots_out["assist_pid"] = shots_out["assist_pid"].astype("Int64")   # nullable int: shot not set up by a pass
    _write_partitioned(shots_out, os.path.join(out, "shots"))
    n = GRID_X * GRID_Y
    heat_tbl = pa.table({
        "whoscored_player_id": pa.array(heat.whoscored_player_id.to_numpy(), pa.int64()),
        "touches": pa.array([a.tolist() for a in heat.touches], pa.list_(pa.uint16(), n)),
        "defs": pa.array([a.tolist() for a in heat.defs], pa.list_(pa.uint16(), n)),
        "league": pa.array(heat.league.tolist()),
        "season": pa.array(heat.season.tolist()),
    })
    _write_partitioned(heat_tbl, os.path.join(out, "heatmaps"))

    if not subset:
        from core.advanced.xg_merge import merge_xg_columns
        merge_xg_columns()

    print(f"\nWrote {len(pm)} player-matches, {len(shots)} shots, {len(heat)} heatmap rows to {out} "
          f"in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
