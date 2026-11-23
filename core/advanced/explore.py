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
from core.advanced import stabilize
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


def scatter_points(df: pd.DataFrame, x_col: str, y_col: str, season: str, league: str | None = None,
                   position_group: str | None = None, min_minutes: int | None = None, limit: int = 2500) -> list[dict]:
    """Every player-season with both metrics present, under the same filters as rank_players.
    Capped at `limit`, keeping the players with the most minutes, so the payload stays small."""
    subset = df[df["season"] == season]
    subset = subset[config.league_mask(subset, league)]
    if position_group and position_group != "all":
        subset = subset[subset["_pos_group"] == position_group]
    floor = min_minutes if min_minutes is not None else config.minutes_floor(subset)
    subset = subset[subset["total_minutes"] >= floor]
    if x_col not in subset.columns or y_col not in subset.columns:
        return []
    subset = subset[subset[x_col].notna() & subset[y_col].notna()]
    subset = subset.sort_values("total_minutes", ascending=False).head(limit)
    return [{"x": float(x), "y": float(y), "name": name, "team": team, "league": lg, "season": season, "group": grp,
             "id": int(pid), "minutes": _clean_minutes(mins)}
            for x, y, name, team, lg, grp, pid, mins in zip(
                subset[x_col].to_numpy(), subset[y_col].to_numpy(), subset["player_name"].to_numpy(),
                subset["team_name"].to_numpy(), subset["league"].to_numpy(), subset["_pos_group"].to_numpy(),
                subset["whoscored_player_id"].to_numpy(), subset["total_minutes"].to_numpy())]


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
    view in the app stays pinned to the stricter default floor. Rows are
    ordered by minutes-adjusted value (see the comment below), so a short
    spell only rises if its rate is extreme enough to survive the adjustment."""
    subset = df[df["season"] == season]
    subset = subset[config.league_mask(subset, league)]
    if position_group and position_group != "all":
        subset = subset[subset["_pos_group"] == position_group]
    minutes_floor = min_minutes if min_minutes is not None else config.minutes_floor(subset)
    subset = subset[subset["total_minutes"] >= minutes_floor]

    if metric_col not in subset.columns:
        return []
    subset = subset[subset[metric_col].notna()]
    if subset.empty:
        return []

    ascending = metric_col in INVERTED_METRICS

    # Ranked on minutes-adjusted values (stabilize.py), the same ones the player page ranks: each
    # value is pulled toward its position group's median by how little evidence stands behind it,
    # so a 90-minute cameo cannot head the list on a lucky rate. The percentile is against the
    # same-season, same-position-group, cross-league cohort, so it matches the player page too.
    k = stabilize.minutes_for_half_signal(metric_col)
    cohorts: dict[str, tuple] = {}      # group -> (adjusted cohort values, centre)
    for group in subset["_pos_group"].dropna().unique():
        mask = (df["season"] == season) & (df["_pos_group"] == group) & (df["total_minutes"] >= config.minutes_floor(df))
        cohort = df.loc[mask, [metric_col, "total_minutes"]].dropna(subset=[metric_col])
        centre = cohort[metric_col].median()
        cohorts[group] = (stabilize.adjusted(cohort[metric_col], cohort["total_minutes"], centre, k)
                          if centre == centre else cohort[metric_col], centre)
    centres = subset["_pos_group"].map(lambda g: cohorts.get(g, (None, float("nan")))[1])
    centres = centres.fillna(subset[metric_col].median())
    subset = subset.assign(_adjusted=stabilize.adjusted(subset[metric_col], subset["total_minutes"], centres, k))
    subset = subset.sort_values("_adjusted", ascending=ascending)

    out = []
    for rank, (_, row) in enumerate(subset.head(limit).iterrows(), start=1):
        # the stored group, not one re-derived from `position`, which is missing for some players
        group = row.get("_pos_group") or pos_group(row.get("position"))
        ranked = cohorts.get(group, (None, None))[0]
        pct = _percentile_rank(row["_adjusted"], ranked, invert=ascending) if ranked is not None else 0

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
            "position_group": {"attacker": "attackers", "midfielder": "midfielders", "defender": "defenders",
                               "goalkeeper": "goalkeepers"}.get(group, "same-position players"),
        })
    return out
