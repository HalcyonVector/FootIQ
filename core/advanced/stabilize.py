"""
Percentiles that account for how much a player has played.

A raw per-90 rate or percentage from 46 minutes is mostly luck: four shots in 46 minutes is 7.8 per
90, top of the scale, and the player page listed it as a strength. Each value is pulled toward the
middle of the comparison group (its median) in proportion to how little evidence stands behind it,
and everyone, the comparison group included, is ranked on those adjusted values:

    adjusted = median + w * (value - median),   w = minutes / (minutes + K)

K is the minutes at which a metric is half signal, half noise. It comes from the data, not a guess:
the season-to-season correlation r of the metric (extras.stability, players with 900+ minutes in two
consecutive seasons, about 2,000 minutes each) is read as the reliability at those minutes, and with
reliability(m) = m / (m + K), K = M * (1 - r) / r. Shots per 90 (r = 0.89) need about 250 minutes;
tackle success (r = 0.09) needs a whole season many times over, so a single season moves it little.
This is the usual empirical-Bayes shrinkage of rates; displayed values stay the real numbers.
"""
import pandas as pd

TYPICAL_MINUTES = 2000.0   # minutes per season of the players the correlations come from
DEFAULT_R = 0.5            # a metric with no correlation on record: half signal at TYPICAL_MINUTES
R_FLOOR, R_CEIL = 0.05, 0.95


def minutes_for_half_signal(col: str) -> float:
    from core.advanced import extras
    info = extras.stability().get(col) or {}
    r = info.get("r", DEFAULT_R)
    r = min(max(r if r == r else DEFAULT_R, R_FLOOR), R_CEIL)
    m = info.get("m", TYPICAL_MINUTES)
    return m * (1 - r) / r


def weight(minutes, k: float):
    """Share of a player's own deviation from the median that is kept: 0 with no minutes, near 1 with many."""
    if isinstance(minutes, pd.Series):
        mins = minutes.fillna(0).clip(lower=0)
        return mins / (mins + k)
    mins = max(float(minutes or 0), 0.0)
    return mins / (mins + k)


def adjusted(value, minutes, centre: float, k: float):
    return centre + weight(minutes, k) * (value - centre)


def cohort_and_player(col: str, value: float, minutes: float, cohort: pd.DataFrame):
    """(adjusted cohort values, adjusted player value) for ranking. The centre is the comparison
    group's median, so a player with almost no minutes lands near the 50th percentile."""
    vals = cohort[col]
    centre = vals.median()
    if centre != centre:               # nobody in the group has this metric
        return vals, value
    k = minutes_for_half_signal(col)
    return adjusted(vals, cohort["total_minutes"], centre, k), adjusted(value, minutes, centre, k)


# Final Third pillar scores blend per-90 volume stats (shots, passes, carries in the final third),
# which repeat well from season to season (r about 0.8): about 500 minutes for half signal.
PILLAR_K = TYPICAL_MINUTES * (1 - 0.8) / 0.8


def adjust_series(values: pd.Series, minutes: pd.Series, k: float) -> tuple:
    """(adjusted values, centre) for a derived score that is not a column of the table."""
    vals = values.reset_index(drop=True)
    mins = minutes.reset_index(drop=True)
    centre = vals.median()
    if centre != centre:
        return vals, centre
    return adjusted(vals, mins, centre, k), centre
