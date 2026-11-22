"""Percentiles account for minutes played: a short spell is pulled toward the middle of the group,
a full season barely moves, and only stats that are mostly signal make the strengths list."""
import pandas as pd

from core.advanced import stabilize
from core.advanced.summary import insights


def test_a_short_spell_is_pulled_to_the_middle_and_a_full_season_is_not():
    k = 250.0                                    # shots per 90: about 250 minutes for half signal
    assert abs(stabilize.adjusted(7.8, 46, 1.2, k) - 1.2) < 1.2          # 7.8 shots/90 in 46' -> about 2.2
    assert abs(stabilize.adjusted(7.8, 3000, 1.2, k) - 7.8) < 0.6        # the same rate over 3000' stays high
    assert stabilize.weight(0, k) == 0 and stabilize.weight(None, k) == 0


def test_minutes_for_half_signal_follow_the_season_to_season_correlation(monkeypatch):
    from core.advanced import extras
    monkeypatch.setattr(extras, "stability", lambda: {"steady": {"r": 0.9}, "noisy": {"r": 0.1}})
    assert stabilize.minutes_for_half_signal("steady") < 300 < 10_000 < stabilize.minutes_for_half_signal("noisy")
    assert stabilize.minutes_for_half_signal("unknown") == stabilize.TYPICAL_MINUTES   # r = 0.5 by default


def test_the_cohort_is_adjusted_by_its_own_minutes():
    cohort = pd.DataFrame({"m": [1.0, 2.0, 3.0, 10.0], "total_minutes": [3000, 3000, 3000, 450]})
    ranked, mine = stabilize.cohort_and_player("m", 10.0, 46, cohort)
    assert ranked.iloc[3] < 10.0 and mine < ranked.iloc[3]      # 46 minutes is pulled in further than 450


def test_strengths_skip_stats_that_are_mostly_luck_at_these_minutes():
    cats = [{"label": "Cat", "rows": [{"stats": [
        {"label": "Shots", "key": "a", "percentile": 95, "value": 7.8, "unit": "", "signal": 0.16},
        {"label": "Key passes", "key": "b", "percentile": 90, "value": 3.0, "unit": "", "signal": 0.8},
    ]}]}]
    assert [s["label"] for s in insights(cats)["strengths"]] == ["Key passes"]
