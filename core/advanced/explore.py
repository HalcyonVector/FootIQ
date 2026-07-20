"""
Ranked stat browsing ("Explore") — the discovery entry point Scout doesn't
cover: Scout requires already knowing a reference player, this lets you rank
every player-season by a single chosen metric instead. Reuses the exact same
cohort conventions as the rest of the app (percentiles.py's min-minutes gate,
core/position.py's grouping) rather than inventing new filtering logic.
"""

import pandas as pd

from core.advanced import config
from core.advanced.lookup import _clean_age, _clean_minutes, _clean_position
from core.advanced.metrics_master import CATEGORIES, CATEGORY_ORDER, INVERTED_METRICS
from core.advanced.percentiles import _percentile_rank
from core.position import pos_group

# Categories with a flat, rankable metric list. Excludes final_third (its
# headline stats are cohort-relative composites, not flat columns — see
# percentiles.py::_build_final_third_stats) and linkup (pairwise, not a
# per-player row).
EXPLORABLE_CATEGORIES = [c for c in CATEGORY_ORDER if c not in ("final_third", "linkup")]


def explorable_metrics() -> list[dict]:
    """{category, category_label, metrics: [{col, label, unit}]} for every
    rankable metric — powers the frontend's category -> metric dropdown."""
    out = []
    for cat_key in EXPLORABLE_CATEGORIES:
        cat = CATEGORIES[cat_key]
        out.append({
            "category": cat_key,
            "category_label": cat["label"],
            "gk_only": cat["gk_only"],
            "metrics": [{"col": col, "label": label, "unit": unit} for col, label, unit in cat["metrics"]],
        })
    return out


def rank_players(
    df: pd.DataFrame,
    metric_col: str,
    season: str,
    league: str | None = None,
    position_group: str | None = None,
    min_minutes: int | None = None,
    limit: int = 25,
) -> list[dict]:
    """Rank every player-season row for `metric_col` within the requested
    filters. Direction (higher-is-better vs lower-is-better) follows the same
    INVERTED_METRICS list every percentile/chart already respects, so e.g.
    'Median release time' correctly ranks fastest-first. `min_minutes` lets
    the caller move the app's own noise floor in either direction — up for
    "starters only", or explicitly down (Explore's lowest UI option is 90,
    not 0) for surfacing a breakout player on a small sample, which a
    discovery tool should allow even though every OTHER cohort/percentile
    view in the app stays pinned to the stricter default floor."""
    subset = df[df["season"] == season]
    if league and league != "all":
        subset = subset[subset["league"] == league]
    if position_group and position_group != "all":
        subset = subset[subset["position"].apply(lambda p: pos_group(p) == position_group)]
    minutes_floor = min_minutes if min_minutes is not None else config.ADV_MIN_MINUTES
    subset = subset[subset["total_minutes"] >= minutes_floor]

    if metric_col not in subset.columns:
        return []
    subset = subset[subset[metric_col].notna()]
    if subset.empty:
        return []

    ascending = metric_col in INVERTED_METRICS
    subset = subset.sort_values(metric_col, ascending=ascending)

    # Percentile is computed against the same-season, same-position-group,
    # cross-league cohort (mirrors percentiles.py's own _cohort) so the color
    # bar means the same thing here as it does on every stat card elsewhere.
    cohorts: dict[str, pd.Series] = {}

    out = []
    for rank, (_, row) in enumerate(subset.head(limit).iterrows(), start=1):
        group = pos_group(row.get("position"))
        if group not in cohorts:
            cohort_mask = (df["season"] == season) & (df["position"].apply(lambda p: pos_group(p) == group)) & (df["total_minutes"] >= config.ADV_MIN_MINUTES)
            cohorts[group] = df.loc[cohort_mask, metric_col]
        pct = _percentile_rank(row[metric_col], cohorts[group], invert=ascending)

        out.append({
            "rank": rank,
            "player_id": int(row.get("whoscored_player_id")),
            "name": row.get("player_name"),
            "team": row.get("team_name"),
            "league": row.get("league"),
            "season": season,
            "position": _clean_position(row.get("position")),
            "age": _clean_age(row.get("age")),
            "minutes": _clean_minutes(row.get("total_minutes")),
            "value": round(float(row[metric_col]), 2),
            "percentile": pct,
        })
    return out
