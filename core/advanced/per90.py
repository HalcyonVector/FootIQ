"""Per-90 rate conversion — a generic utility, extracted from the old
CSV-backed core/normalizer.py (now retired) since core/advanced/aggregator.py
still needs it."""


def per_90(value: float, minutes: int) -> float:
    """Return stat scaled to per-90-minute rate. Returns 0.0 on bad input."""
    if not minutes or minutes < 1:
        return 0.0
    return round((value / minutes) * 90, 3)
