"""
Lazy-loaded, memoized access to the precomputed advanced-metrics parquet.
Mirrors core/fetcher.py's _get_df() pattern for the FBref CSV — the running
app only ever reads this small file, never the 6GB raw event cache.
"""

import os
import pandas as pd

from core.advanced import config

_DF: pd.DataFrame | None = None
_LINKUP_DF: pd.DataFrame | None = None
_CHART_EVENTS_DF: pd.DataFrame | None = None


def get_advanced_df() -> pd.DataFrame:
    global _DF
    if _DF is None:
        if os.path.exists(config.PLAYER_SEASON_PARQUET):
            _DF = pd.read_parquet(config.PLAYER_SEASON_PARQUET)
            if not _DF.empty:
                from core.media import _normalize_str
                from core.position import pos_group
                # Precomputed once here instead of re-normalizing every
                # player's name / re-classifying every player's position
                # group on every single search/Scout/Explore request —
                # turns a per-request O(n) Python-level pass into a
                # one-time cost at load/reload.
                _DF["_norm_name"] = _DF["player_name"].map(lambda p: _normalize_str(str(p)))
                _DF["_pos_group"] = _DF["position"].map(pos_group)
        else:
            _DF = pd.DataFrame()
    return _DF


def get_linkup_df() -> pd.DataFrame:
    global _LINKUP_DF
    if _LINKUP_DF is None:
        if os.path.exists(config.LINKUP_PAIRS_PARQUET):
            _LINKUP_DF = pd.read_parquet(config.LINKUP_PAIRS_PARQUET)
        else:
            _LINKUP_DF = pd.DataFrame()
    return _LINKUP_DF


def get_chart_events_df() -> pd.DataFrame:
    """Per-category raw chart-event coordinates (evt_<category>_<field> list
    columns) — only loaded when a chart is actually requested, never on the
    /api/advanced-stats fast path."""
    global _CHART_EVENTS_DF
    if _CHART_EVENTS_DF is None:
        if os.path.exists(config.CHART_EVENTS_PARQUET):
            _CHART_EVENTS_DF = pd.read_parquet(config.CHART_EVENTS_PARQUET)
        else:
            _CHART_EVENTS_DF = pd.DataFrame()
    return _CHART_EVENTS_DF


def reload():
    """Force a re-read from disk (e.g. after rebuilding the parquet)."""
    global _DF, _LINKUP_DF, _CHART_EVENTS_DF
    _DF = None
    _LINKUP_DF = None
    _CHART_EVENTS_DF = None
    return get_advanced_df()
