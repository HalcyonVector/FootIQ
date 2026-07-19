"""
Position-weighted composite rating — a single 0-100 headline number per
player, in the same spirit as the "match rating" style scores popular sites
(WhoScored, Sofascore, FotMob) show, but built entirely from percentiles
this app already computes rather than a separate proprietary formula.

Method: each Advanced Metrics category's percentile stats are averaged into
one category-level percentile (skipping any stat gated to "no_data" by its
own min-sample threshold), then those category percentiles are combined via
a WEIGHTED average, with weights chosen per position group to reflect what
actually matters for that role — a center-back's rating should hinge on
defending/aerial duels, not on shot conversion. Weights are a judgment call
(there's no single universally "correct" rating formula for this level of
event-derived data), not a literal reproduction of any one site's methodology.
Weights are renormalized over whichever categories the player actually has
data for, so a category with zero minutes contribution (e.g. Goalkeeping
data present for keepers is 80%+ of the score; that data source doesn't get
diluted for a keeper just because they had a bad clean-sheet-less month.
"""
from core.advanced.metrics_master import CATEGORY_ORDER
from core.position import pos_group

# category_key -> weight, per position group. Excludes "linkup" (pairwise,
# not a per-player percentile category) everywhere. Weights sum to 1.0 per
# group; a category missing from a group's dict is simply weight 0 for it.
CATEGORY_WEIGHTS = {
    "attacker": {
        "shooting": 0.28, "final_third": 0.18, "carrying": 0.14,
        "decision_making": 0.10, "passing": 0.10, "half_spaces": 0.06,
        "aerial": 0.06, "tempo": 0.04, "holdup": 0.04,
    },
    "midfielder": {
        "passing": 0.22, "decision_making": 0.16, "defending": 0.14,
        "carrying": 0.12, "half_spaces": 0.10, "tempo": 0.08,
        "post_recovery": 0.08, "final_third": 0.06, "aerial": 0.04,
    },
    "defender": {
        "defending": 0.32, "aerial": 0.18, "passing": 0.14,
        "post_recovery": 0.12, "holdup": 0.08, "half_spaces": 0.06,
        "carrying": 0.06, "decision_making": 0.04,
    },
    "goalkeeper": {
        "goalkeeping": 0.85, "passing": 0.15,
    },
}


def category_percentile(cat: dict) -> float | None:
    """Mean percentile across a category's non-"no_data" stats — None if the
    category has zero usable stats (e.g. a keeper's hidden outfield tabs
    that build_all_categories doesn't even return, or genuinely no sample)."""
    if not cat or not cat.get("rows"):
        return None
    stats = cat["rows"][0].get("stats") or []
    valid = [s["percentile"] for s in stats if not s.get("no_data") and s.get("percentile") is not None]
    if not valid:
        return None
    return sum(valid) / len(valid)


def compute_composite(cats: list[dict], position: str) -> dict:
    """Returns {"score": float|None, "breakdown": {category_key: pct}} — score
    is None only if literally none of the player's categories have any data
    (shouldn't happen in practice above the app's minutes threshold)."""
    group = pos_group(position)
    weights = CATEGORY_WEIGHTS.get(group, CATEGORY_WEIGHTS["midfielder"])
    by_key = {c["key"]: c for c in cats}

    weighted_sum = 0.0
    total_weight = 0.0
    breakdown = {}
    for cat_key in CATEGORY_ORDER:
        if cat_key == "linkup" or cat_key not in weights:
            continue
        pct = category_percentile(by_key.get(cat_key))
        if pct is None:
            continue
        breakdown[cat_key] = round(pct, 1)
        weighted_sum += pct * weights[cat_key]
        total_weight += weights[cat_key]

    if total_weight == 0:
        return {"score": None, "breakdown": breakdown}
    return {"score": round(weighted_sum / total_weight, 1), "breakdown": breakdown}
