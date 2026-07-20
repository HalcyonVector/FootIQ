"""Unit tests for core/advanced/composite.py — mainly the power-mean
aggregation (COMPOSITE_POWER) that replaced a flat weighted average, since
that's the part of this module with actual math to get wrong."""
import pytest

from core.advanced.composite import category_percentile, compute_composite, CATEGORY_WEIGHTS


def _cat(key: str, percentiles: list[float | None]) -> dict:
    """Build a minimal category dict compute_composite()/category_percentile()
    can read — shape matches what build_all_categories() actually returns."""
    stats = [{"percentile": p, "no_data": p is None} for p in percentiles]
    return {"key": key, "rows": [{"stats": stats}]}


def test_category_percentile_averages_valid_stats():
    cat = _cat("passing", [80, 60, 40])
    assert category_percentile(cat) == pytest.approx(60.0)


def test_category_percentile_skips_no_data_stats():
    cat = _cat("passing", [80, None, 40])
    assert category_percentile(cat) == pytest.approx(60.0)


def test_category_percentile_none_when_all_no_data():
    cat = _cat("passing", [None, None])
    assert category_percentile(cat) is None


def test_category_percentile_none_for_empty_rows():
    assert category_percentile({"key": "passing", "rows": []}) is None
    assert category_percentile(None) is None


def test_compute_composite_none_when_no_categories_have_data():
    result = compute_composite([], "FW")
    assert result["score"] is None
    assert result["breakdown"] == {}


def test_compute_composite_flat_profile_equals_that_value():
    # If every relevant category sits at exactly the same percentile, the
    # power mean must return that same value regardless of COMPOSITE_POWER
    # (this is the one input where a power mean and a flat average agree).
    group_weights = CATEGORY_WEIGHTS["midfielder"]
    cats = [_cat(key, [55.0]) for key in group_weights]
    result = compute_composite(cats, "MC")
    assert result["score"] == pytest.approx(55.0, abs=0.5)


def test_compute_composite_rewards_a_specialist_over_a_flat_profile():
    # Same average percentile (~55), but one profile is "spiky" (elite at
    # their main job, weak elsewhere) and the other is uniformly average.
    # The power mean should score the specialist higher — that's the whole
    # point of switching away from a flat weighted average.
    group_weights = CATEGORY_WEIGHTS["attacker"]
    keys = list(group_weights)
    flat_cats = [_cat(k, [55.0]) for k in keys]
    n = len(keys)
    spiky_values = [95.0] + [ (55.0 * n - 95.0) / (n - 1) ] * (n - 1)
    spiky_cats = [_cat(k, [v]) for k, v in zip(keys, spiky_values)]

    flat_score = compute_composite(flat_cats, "FW")["score"]
    spiky_score = compute_composite(spiky_cats, "FW")["score"]

    assert spiky_score > flat_score


def test_compute_composite_score_bounded_0_to_100():
    group_weights = CATEGORY_WEIGHTS["defender"]
    cats = [_cat(key, [100.0]) for key in group_weights]
    result = compute_composite(cats, "DC")
    assert 0 <= result["score"] <= 100


def test_compute_composite_ignores_linkup_and_unweighted_categories():
    cats = [
        _cat("linkup", [10.0]),        # excluded everywhere by design
        _cat("not_a_real_category", [10.0]),
    ]
    result = compute_composite(cats, "FW")
    assert result["score"] is None
    assert "linkup" not in result["breakdown"]


def test_goalkeeper_weights_dominated_by_goalkeeping_category():
    assert CATEGORY_WEIGHTS["goalkeeper"]["goalkeeping"] > CATEGORY_WEIGHTS["goalkeeper"]["passing"]


@pytest.mark.parametrize("group", ["attacker", "midfielder", "defender", "goalkeeper"])
def test_each_position_groups_weights_sum_to_one(group):
    assert sum(CATEGORY_WEIGHTS[group].values()) == pytest.approx(1.0)
