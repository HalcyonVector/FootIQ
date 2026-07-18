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


def get_advanced_df() -> pd.DataFrame:
    global _DF
    if _DF is None:
        if os.path.exists(config.PLAYER_SEASON_PARQUET):
            _DF = pd.read_parquet(config.PLAYER_SEASON_PARQUET)
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


def reload():
    """Force a re-read from disk (e.g. after rebuilding the parquet)."""
    global _DF, _LINKUP_DF
    _DF = None
    _LINKUP_DF = None
    return get_advanced_df()
