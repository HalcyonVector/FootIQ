"""
Scout — whole-profile percentile-vector similarity search. Pools players
across ALL 5 leagues and all 3 seasons for the target's position group
(unlike the Advanced Metrics tab's own cohort in percentiles.py, which is
scoped to one league-season at a time) — a Ligue 1 full-back a season ago is
just as valid a "similar player" as one playing in the Premier League today.

Similarity is cosine distance between each player's percentile vector across
the same metric set build_all_categories would show for that position group,
comparing two players only on the metrics BOTH have data for (rather than
treating a missing metric as 0, which would penalize players for gaps in
event coverage rather than genuine statistical difference).
"""
import pandas as pd

from core.advanced import config
from core.advanced.lookup import _clean_position, _clean_minutes, _clean_age
from core.advanced.metrics_master import CATEGORIES, CATEGORY_ORDER, INVERTED_METRICS
from core.advanced.percentiles import GK_VISIBLE_OUTFIELD_CATEGORIES
from core.position import pos_group

MIN_COMMON_METRICS = 8  # below this, two profiles don't overlap enough to compare meaningfully

# pos_group -> (cohort_df, percentile_df, source_len) — rebuilt whenever the
# underlying advanced_df's row count changes (i.e. after a rebuild + reload).
_PCT_CACHE: dict = {}


def _metric_columns_for(position_group: str) -> list[str]:
    """Same metric set build_all_categories() would show for this position
    group (GK-gated the same way), flattened to one column list."""
    is_gk = position_group == "goalkeeper"
    cols = []
    for cat_key in CATEGORY_ORDER:
        cat = CATEGORIES[cat_key]
        if cat["gk_only"] and not is_gk:
            continue
        if not cat["gk_only"] and is_gk and cat_key not in GK_VISIBLE_OUTFIELD_CATEGORIES:
            continue
        cols.extend(col for col, _label, _unit in cat["metrics"])
    return cols


def _cross_cohort(df: pd.DataFrame, position: str) -> pd.DataFrame:
    """Every league+season row for this position group with enough minutes —
    NOT filtered to one season/league, unlike percentiles._cohort()."""
    group = pos_group(position)
    subset = df[df["position"].apply(lambda p: pos_group(p) == group)]
    subset = subset[subset["total_minutes"] >= config.ADV_MIN_MINUTES]
    return subset


def _percentile_matrix(cohort: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Vectorized cohort-wide percentile rank per metric column (0-100),
    inverted where a lower raw value is better (INVERTED_METRICS). NaN stays
    NaN so two players are only compared on metrics they both have."""
    out = {}
    for col in cols:
        if col not in cohort.columns:
            continue
        ranked = cohort[col].rank(pct=True, na_option="keep") * 100
        out[col] = (100 - ranked) if col in INVERTED_METRICS else ranked
    return pd.DataFrame(out, index=cohort.index)


def _get_percentiles(df: pd.DataFrame, position_group: str) -> tuple:
    cached = _PCT_CACHE.get(position_group)
    if cached is not None and cached[2] == len(df):
        return cached[0], cached[1]
    cohort = _cross_cohort(df, position_group)
    cols = _metric_columns_for(position_group)
    pct = _percentile_matrix(cohort, cols)
    _PCT_CACHE[position_group] = (cohort, pct, len(df))
    return cohort, pct


def find_similar(df: pd.DataFrame, target_pid: int, target_league: str, target_season: str,
                  limit: int = 20, max_age: int | None = None, leagues: list[str] | None = None) -> tuple:
    """Up to `limit` most statistically-similar OTHER REAL PLAYERS (never the
    target — not just their exact league/season row, but every season of
    theirs, since the cohort pools across seasons and a player's own other
    years are trivially "similar" to themselves) ranked by cosine similarity
    of percentile vectors. Each real player contributes at most one result —
    their single best-matching season — rather than occupying several slots
    just because they have multiple qualifying seasons.
    `max_age`/`leagues` filter which CANDIDATES are eligible — they never
    affect the percentile computation itself, which always ranks against the
    full cross-league/season position cohort regardless of these filters.
    Returns (matches, widened) — widened=True if the filters excluded every
    candidate and were dropped to show the best available matches instead."""
    target_rows = df[(df["whoscored_player_id"] == int(target_pid)) & (df["league"] == target_league) & (df["season"] == target_season)]
    if target_rows.empty:
        return [], False
    target_row = target_rows.iloc[0]
    target_pid_int = int(target_row["whoscored_player_id"])
    position_group = pos_group(target_row.get("position"))

    cohort, pct = _get_percentiles(df, position_group)
    if target_row.name not in pct.index:
        return [], False

    target_vec = pct.loc[target_row.name].dropna()
    if target_vec.empty:
        return [], False

    pid_by_idx = cohort["whoscored_player_id"]

    scored = []
    for idx, row_pct in pct.iterrows():
        if int(pid_by_idx.loc[idx]) == target_pid_int:
            continue  # exclude EVERY season of the target's own — not just this exact row
        common = target_vec.index.intersection(row_pct.dropna().index)
        if len(common) < MIN_COMMON_METRICS:
            continue
        a = target_vec[common].to_numpy()
        b = row_pct[common].to_numpy()
        denom = (a @ a) ** 0.5 * (b @ b) ** 0.5
        if denom == 0:
            continue
        scored.append((float((a @ b) / denom), idx))

    scored.sort(key=lambda t: t[0], reverse=True)

    # One result per real player: since `scored` is already sorted by
    # similarity descending, the first occurrence of a player_id we see IS
    # their best-matching season — later occurrences are strictly worse and
    # just dropped.
    seen_pids: set = set()
    deduped = []
    for similarity, idx in scored:
        pid = int(pid_by_idx.loc[idx])
        if pid in seen_pids:
            continue
        seen_pids.add(pid)
        deduped.append((similarity, idx))

    def _passes(idx) -> bool:
        r = cohort.loc[idx]
        if max_age is not None:
            age = _clean_age(r.get("age"))
            if age is None or age > max_age:  # unknown age treated as "doesn't qualify", not benefit-of-the-doubt
                return False
        if leagues and r["league"] not in leagues:
            return False
        return True

    filtered = [(s, idx) for s, idx in deduped if _passes(idx)]
    widened = False
    if not filtered and (max_age is not None or leagues) and deduped:
        filtered = deduped
        widened = True

    out = []
    for similarity, idx in filtered[:limit]:
        r = cohort.loc[idx]
        out.append({
            "player_id": int(r["whoscored_player_id"]), "name": r["player_name"], "team": r["team_name"],
            "league": r["league"], "season": r["season"], "position": _clean_position(r["position"]),
            "minutes": _clean_minutes(r["total_minutes"]), "age": _clean_age(r.get("age")),
            "similarity": round(similarity * 100, 1),
        })
    return out, widened
