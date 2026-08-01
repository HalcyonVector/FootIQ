"""
Cohort-based percentile calculation, mirroring core/insights.py's pattern:
filter to same position-group + season + minutes >= ADV_MIN_MINUTES, then
rank the player's value within that cohort. True percentile-within-cohort
rather than a fixed max-val scale, since these ~70 metrics don't have
hand-tuned max values the way core/scorer.py's _MASTER_METRICS do.
"""

import statistics

import pandas as pd

from core.advanced import config
from core.advanced.categories.final_third import pillar_floor_scores, pillar_per_touch_scores
from core.advanced.metrics_master import CATEGORIES, CATEGORY_ORDER, INVERTED_METRICS
from core.position import pos_group

PILLAR_NAMES = ("shooting", "linkup", "carrying", "ballwinning")
PILLAR_LABELS = {"shooting": "Shooting", "linkup": "Link-Up", "carrying": "Carrying", "ballwinning": "Ball Winning"}


def _cohort(df: pd.DataFrame, position: str, league_agnostic_season: str) -> pd.DataFrame:
    group = pos_group(position)
    subset = df[df["season"] == league_agnostic_season]
    subset = subset[subset["_pos_group"] == group]
    subset = subset[subset["total_minutes"] >= config.ADV_MIN_MINUTES]
    return subset


def build_cohort(df: pd.DataFrame, position: str, season: str) -> pd.DataFrame:
    """Public entry point for callers outside this module (e.g. app.py's
    chart endpoints) that need the same same-position/same-season/min-minutes
    cohort `build_all_categories` uses internally."""
    return _cohort(df, position, season)


def _percentile_rank(value: float, series: pd.Series, invert: bool = False) -> int:
    """invert=True for "lower raw value is better" metrics (release times,
    fouls conceded, dangerous losses...) so a fast/clean player still lands
    at the high end of the 0-100 scale instead of the low end."""
    valid = series.dropna()
    if len(valid) < 5 or value is None:
        return 0
    pct = int(round((valid < value).mean() * 100))
    return 100 - pct if invert else pct


def _completeness_impact(floor_pct: dict, per_touch_pct: dict, have_data: bool) -> tuple:
    """Completeness rewards the floor (geometric mean across all 4 pillar
    percentiles, penalized by how spread out they are) — Impact rewards the
    ceiling (mean per-touch percentile of the player's 2 strongest pillars)."""
    if not have_data:
        return None, None
    fracs = [max(floor_pct[p], 1) / 100 for p in PILLAR_NAMES]  # floor of 1 avoids a zero collapsing the geomean
    geomean = statistics.geometric_mean(fracs) * 100
    spread_penalty = 1 - (statistics.pstdev(list(floor_pct.values())) / 100)
    completeness = round(geomean * max(0, spread_penalty), 1)

    top2 = sorted(PILLAR_NAMES, key=lambda p: floor_pct[p], reverse=True)[:2]
    impact = round(statistics.mean(per_touch_pct[p] for p in top2), 1)
    return completeness, impact


def final_third_pillar_percentiles(row: dict, cohort: pd.DataFrame) -> tuple:
    """Percentile-rank a player's 4 pillar floor/per-touch scores against the
    cohort's own distribution of those same (derived, not flat-column) scores.
    Shared by the Completeness/Impact stat-card composite and the Final Third
    tab's pillar bar chart, so both read the exact same numbers."""
    player_floor = pillar_floor_scores(row)
    player_per_touch = pillar_per_touch_scores(row)

    cohort_records = cohort.to_dict("records")
    cohort_floor = {p: pd.Series([pillar_floor_scores(r)[p] for r in cohort_records]) for p in PILLAR_NAMES}
    cohort_per_touch = {p: pd.Series([pillar_per_touch_scores(r)[p] for r in cohort_records]) for p in PILLAR_NAMES}

    floor_pct = {p: _percentile_rank(player_floor[p], cohort_floor[p]) for p in PILLAR_NAMES}
    per_touch_pct = {p: _percentile_rank(player_per_touch[p], cohort_per_touch[p]) for p in PILLAR_NAMES}
    return floor_pct, per_touch_pct, player_floor, player_per_touch


def _build_final_third_stats(row: dict, cohort: pd.DataFrame) -> list[dict]:
    """Completeness/Impact composites need the whole cohort's pillar-score
    DISTRIBUTIONS to percentile-rank against — this can't be a flat column
    lookup like every other category, so it's handled separately here."""
    floor_pct, per_touch_pct, player_floor, player_per_touch = final_third_pillar_percentiles(row, cohort)

    have_data = bool(row.get("ft_touches_p90") and len(cohort) >= 5)
    completeness, impact = _completeness_impact(floor_pct, per_touch_pct, have_data)

    stats = [
        {"label": "Completeness", "value": completeness if completeness is not None else 0,
         "percentile": int(completeness) if completeness is not None else 0,
         "unit": "", "no_data": completeness is None},
        {"label": "Impact", "value": impact if impact is not None else 0,
         "percentile": int(impact) if impact is not None else 0,
         "unit": "", "no_data": impact is None},
    ]
    for p in PILLAR_NAMES:
        stats.append({"label": f"{PILLAR_LABELS[p]} (floor)", "value": round(player_floor[p], 2),
                       "percentile": floor_pct[p], "unit": ""})
    for p in PILLAR_NAMES:
        stats.append({"label": f"{PILLAR_LABELS[p]} (per touch)", "value": round(player_per_touch[p], 3),
                       "percentile": per_touch_pct[p], "unit": ""})

    for col, label in (("ft_touches_p90", "Final-third touches"), ("ft_shots_p90", "Final-third shots"),
                        ("ft_passes_p90", "Final-third passes"), ("ft_carries_p90", "Final-third carries")):
        value = row.get(col)
        no_data = value is None or (isinstance(value, float) and pd.isna(value))
        stats.append({
            "label": label, "value": round(float(value), 2) if not no_data else 0,
            "percentile": _percentile_rank(value, cohort[col]) if not no_data and col in cohort.columns else 0,
            "unit": "", "no_data": no_data,
        })

    return stats


def build_final_third_scatter(position: str, season: str, df: pd.DataFrame, target_pid: int) -> list[dict]:
    """Completeness/Impact for every player in target_pid's cohort, for the
    Final Third scatter chart — a request-time computation (not precomputed)
    since cohorts are small (tens to low hundreds of players)."""
    cohort = _cohort(df, position, season)
    records = cohort.to_dict("records")
    cohort_floor = {p: pd.Series([pillar_floor_scores(r)[p] for r in records]) for p in PILLAR_NAMES}
    cohort_per_touch = {p: pd.Series([pillar_per_touch_scores(r)[p] for r in records]) for p in PILLAR_NAMES}

    points = []
    for r in records:
        if not r.get("ft_touches_p90"):
            continue
        floor = pillar_floor_scores(r)
        per_touch = pillar_per_touch_scores(r)
        floor_pct = {p: _percentile_rank(floor[p], cohort_floor[p]) for p in PILLAR_NAMES}
        per_touch_pct = {p: _percentile_rank(per_touch[p], cohort_per_touch[p]) for p in PILLAR_NAMES}
        completeness, impact = _completeness_impact(floor_pct, per_touch_pct, True)
        points.append({
            "name": r.get("player_name"), "completeness": completeness, "impact": impact,
            "is_target": int(r.get("whoscored_player_id")) == int(target_pid),
        })
    return points


# Keepers still pass the ball and link up with teammates, so these two stay
# visible alongside Goalkeeping — every other outfield category (Carrying,
# Aerial Duels, etc.) is hidden since it isn't a meaningful GK stat.
GK_VISIBLE_OUTFIELD_CATEGORIES = {"passing", "linkup"}


def build_all_categories(row: dict, position: str, season: str, df: pd.DataFrame) -> list[dict]:
    """row: the player's own record from the advanced parquet (as a dict).
    Returns a list of {key, label, desc, rows: [{player_name, team, photo, stats}]}
    ready for the frontend's renderStatCard, one entry per category (GK-gated)."""
    is_gk = pos_group(position) == "goalkeeper"
    cohort = _cohort(df, position, season)

    out = []
    for cat_key in CATEGORY_ORDER:
        cat = CATEGORIES[cat_key]
        if cat["gk_only"] and not is_gk:
            continue
        if not cat["gk_only"] and is_gk and cat_key not in GK_VISIBLE_OUTFIELD_CATEGORIES:
            continue

        if cat_key == "final_third":
            stats = _build_final_third_stats(row, cohort)
        elif cat_key == "linkup":
            stats = []  # rendered by the frontend from the linkup endpoints, not this stat table
        else:
            stats = []
            for col, label, unit in cat["metrics"]:
                value = row.get(col)
                if value is None or (isinstance(value, float) and pd.isna(value)):
                    stats.append({"label": label, "value": 0, "percentile": 0, "unit": unit, "no_data": True})
                    continue
                pct = _percentile_rank(value, cohort[col], invert=col in INVERTED_METRICS) if col in cohort.columns else 0
                stats.append({"label": label, "value": round(float(value), 2), "percentile": pct, "unit": unit})

        out.append({
            "key": cat_key,
            "label": cat["label"],
            "desc": cat.get("desc", ""),
            "rows": [{
                "player_name": row.get("player_name"),
                "team": row.get("team_name"),
                "photo": "",
                "stats": stats,
            }],
        })

    return out
