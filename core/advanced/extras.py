"""
Figures derived from the whole dataset that a request should not have to recompute.

* the home page's facts and the four featured players' radar numbers (the first visit used to
  spend about a CPU-second on them, which on the throttled free-tier host is ten seconds)
* how repeatable each metric is from one season to the next (the "reliability" shown next to
  a percentile)
* per competition-season coverage (the /coverage page)

`scraping/build_extras.py` writes them to data/advanced/extras.json, which ships inside the
data release. The app reads that file; if it is missing, or was built from a different
player-season table than the one loaded (a different row count), every accessor falls back to
computing the same thing on demand, so the file is a speed-up and never a source of truth.
"""
import json
import math
import os
import re

from core.advanced import config

EXTRAS_JSON = os.path.join(config.ADVANCED_DATA_DIR, "extras.json")
FEATURED_NAMES = ["Erling Haaland", "Mohamed Salah", "Bukayo Saka", "Virgil van Dijk"]

# Season-to-season correlation bands for the reliability label.
HIGH_R, MEDIUM_R = 0.70, 0.45
STABILITY_MIN_MINUTES = 900
STABILITY_MIN_PAIRS = 150

_loaded: dict = {}          # {"file": dict | None}


# ── home page ───────────────────────────────────────────────────────────────

def compute_hub_facts(df) -> dict:
    from core.advanced import store
    from core.advanced.lookup import search_players_global
    from core.advanced.metrics_master import CATEGORIES
    counts = df["season"].value_counts()
    full_season = max((s for s, c in counts.items() if c >= 0.9 * counts.max()), key=config.season_sort_key)
    matches = 0
    try:
        ds = store._overview_dataset("matches", config.PLAYER_MATCHES_DIR)
        matches = len(set(ds.to_table(columns=["match_key"]).column("match_key").to_pylist()))
    except Exception:
        pass
    featured = []
    for name in FEATURED_NAMES:
        hit = search_players_global(name, full_season)
        if hit:
            featured.append({k: hit[0][k] for k in ("id", "name", "team", "league", "season")})
    return {"matches": matches, "players": int(df["whoscored_player_id"].nunique()),
            "metrics": sum(len(c["metrics"]) for c in CATEGORIES.values()),
            "season": full_season, "featured": featured}


def compute_hub_player(p: dict, df) -> dict:
    """Real numbers for one featured player: the radar percentiles, goals and assists."""
    from core.advanced import store, summary
    from core.advanced.identity import match_to_advanced_row
    from core.advanced.percentiles import build_all_categories
    from visuals import specs as sp
    row = match_to_advanced_row(p["id"], p["league"], p["season"], df)
    cats = build_all_categories(row, row.get("position", ""), p["season"], df)
    axes = [{"label": lbl, "value": round(sp._percentile_for(cats, k, l))}
            for (k, l), lbl in zip(sp.RADAR_METRICS, sp.RADAR_LABELS)]
    line = summary.season_line(store.get_player_matches(p["id"], p["league"], p["season"]))
    return {**p, "axes": axes, "goals": line["goals"], "assists": line["assists"],
            "final_third": next((a["value"] for a in axes if a["label"] == "Final Third"), None)}


# ── reliability of each metric ─────────────────────────────────────────────

def tier_for(r) -> str | None:
    if r is None:
        return None
    return "high" if r >= HIGH_R else "medium" if r >= MEDIUM_R else "low"


def compute_stability(df) -> dict:
    """{column: {"r": float, "n": int, "tier": "high"|"medium"|"low"}} -- the correlation of a
    player's value in one domestic season with the next, over players with at least 900 minutes
    in both (consecutive finished seasons pooled). High r means a single season already says
    something stable about the player; low r means the number is mostly noise at that sample."""
    import pandas as pd
    from core.advanced.metrics_master import CATEGORIES
    seasons = sorted({s for s in df["season"].unique() if re.fullmatch(r"\d{4}-\d{2}", str(s))})
    counts = df[df["season"].isin(seasons)]["season"].value_counts()
    full = [s for s in seasons if counts[s] >= 0.9 * counts.max()]          # finished seasons only
    # one row per player per season: the one with most minutes (their league, not a cup run)
    d = df[df["season"].isin(full) & (df["total_minutes"] >= STABILITY_MIN_MINUTES)]
    d = d.loc[d.groupby(["whoscored_player_id", "season"])["total_minutes"].idxmax()]
    cols = [m[0] for c in CATEGORIES.values() for m in c["metrics"] if m[0] in d.columns]
    pairs = []
    for a, b in zip(full, full[1:]):
        x = d[d["season"] == a].set_index("whoscored_player_id")
        y = d[d["season"] == b].set_index("whoscored_player_id")
        ix = x.index.intersection(y.index)
        pairs.append((x.loc[ix], y.loc[ix]))
    out = {}
    for col in dict.fromkeys(cols):
        xs, ys = [], []
        for x, y in pairs:
            xs.append(pd.to_numeric(x[col], errors="coerce"))
            ys.append(pd.to_numeric(y[col], errors="coerce"))
        if not xs:
            continue
        xa, ya = pd.concat(xs, ignore_index=True), pd.concat(ys, ignore_index=True)
        m = xa.notna() & ya.notna()
        if m.sum() < STABILITY_MIN_PAIRS or xa[m].nunique() < 3 or ya[m].nunique() < 3:
            continue
        r = float(xa[m].corr(ya[m]))
        if math.isnan(r):
            continue
        out[col] = {"r": round(r, 2), "n": int(m.sum()), "tier": tier_for(r)}
    return out


# ── coverage ────────────────────────────────────────────────────────────────

def compute_coverage(df) -> list[dict]:
    import pandas as pd
    from core.advanced import store
    matches = {}
    try:
        ds = store._overview_dataset("matches", config.PLAYER_MATCHES_DIR)
        t = ds.to_table(columns=["league", "season", "match_key"]).to_pandas().drop_duplicates()
        matches = t.groupby(["league", "season"])["match_key"].nunique().to_dict()
    except Exception:
        pass
    g = df.groupby(["league", "season"])
    rows = []
    for (league, season), part in g:
        prog = float(part["season_progress"].dropna().iloc[0]) if "season_progress" in part and part["season_progress"].notna().any() else 1.0
        floor = config.minutes_floor(part)          # a number, or one per row while a season is in progress
        ranked = int((part["total_minutes"] >= floor).sum())
        rows.append({"league": league, "season": season, "matches": int(matches.get((league, season), 0)),
                     "players": int(len(part)), "ranked": ranked,
                     "progress": round(prog, 2)})
    rows.sort(key=lambda r: (-config.season_sort_key(r["season"]), r["league"]))
    return rows


# ── build / load ────────────────────────────────────────────────────────────

def build(df=None) -> dict:
    from core.advanced import store
    df = store.get_advanced_df() if df is None else df
    facts = compute_hub_facts(df)
    out = {"rows": int(len(df)), "hub": {"facts": facts,
                                        "players": [compute_hub_player(p, df) for p in facts["featured"]]},
           "stability": compute_stability(df), "coverage": compute_coverage(df)}
    with open(EXTRAS_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    return out


def _file() -> dict | None:
    """The built file, if it exists and matches the player-season table in memory."""
    if "file" not in _loaded:
        data = None
        try:
            with open(EXTRAS_JSON, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
        _loaded["file"] = data
    data = _loaded["file"]
    if data is None:
        return None
    from core.advanced import store
    return data if data.get("rows") == len(store.get_advanced_df()) else None


def reset() -> None:
    _loaded.clear()


def hub_facts() -> dict:
    f = _file()
    if f:
        return f["hub"]["facts"]
    if "hub_facts" not in _loaded:
        from core.advanced import store
        _loaded["hub_facts"] = compute_hub_facts(store.get_advanced_df())
    return _loaded["hub_facts"]


def hub_player(i: int) -> dict:
    f = _file()
    if f and i < len(f["hub"]["players"]):
        return f["hub"]["players"][i]
    key = ("hub_player", i)
    if key not in _loaded:
        from core.advanced import store
        _loaded[key] = compute_hub_player(hub_facts()["featured"][i], store.get_advanced_df())
    return _loaded[key]


def stability() -> dict:
    f = _file()
    if f:
        return f["stability"]
    if "stability" not in _loaded:
        from core.advanced import store
        _loaded["stability"] = compute_stability(store.get_advanced_df())
    return _loaded["stability"]


def coverage() -> list[dict]:
    f = _file()
    if f:
        return f["coverage"]
    if "coverage" not in _loaded:
        from core.advanced import store
        _loaded["coverage"] = compute_coverage(store.get_advanced_df())
    return _loaded["coverage"]
