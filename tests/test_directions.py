"""Every place that ranks a metric agrees on which way is better."""
from core.advanced.metrics_master import INVERTED_METRICS
from core.advanced import quadrants


def test_goals_conceded_ranks_the_keeper_who_concedes_least_highest():
    assert "gk_goals_conceded_count_p90" in INVERTED_METRICS


def test_quadrant_lower_is_better_columns_are_in_the_shared_list():
    # The quadrant plots once flipped goals conceded on their own while the percentiles did not, so
    # the Goalkeeping tab listed conceding the most as a strength. Any column a plot treats as
    # lower-is-better must be in INVERTED_METRICS too.
    lower = {c for p in quadrants.PRESETS for axis in (p["x"], p["y"]) for c in axis["lower"]}
    assert lower <= INVERTED_METRICS, lower - INVERTED_METRICS

