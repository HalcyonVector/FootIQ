"""
Per-90 normalization.
Converts raw cumulative stats → rate stats (per 90 minutes played).
"""


def per_90(value: float, minutes: int) -> float:
    """Return stat scaled to per-90-minute rate. Returns 0.0 on bad input."""
    if not minutes or minutes < 1:
        return 0.0
    return round((value / minutes) * 90, 3)


def normalize_stats(raw: dict) -> dict:
    """
    Take raw player stats dict (from fetcher) and return an enriched copy
    with all per-90 and rate metrics added.
    """
    mins = raw.get("minutes", 0) or 0

    norm = dict(raw)  # keep all identity fields

    # --- Per-90 attacking ---
    norm["goals_p90"]      = per_90(raw.get("goals", 0), mins)
    norm["assists_p90"]    = per_90(raw.get("assists", 0), mins)
    norm["shots_on_p90"]   = per_90(raw.get("shots_on", 0), mins)
    norm["shots_total_p90"]= per_90(raw.get("shots_total", 0), mins)
    norm["xg_p90"]         = per_90(raw.get("xg", 0), mins)
    norm["xag_p90"]        = per_90(raw.get("xag", 0), mins)

    # --- Per-90 passing ---
    norm["key_passes_p90"]       = per_90(raw.get("passes_key", 0), mins)
    norm["pass_accuracy"]        = raw.get("pass_accuracy", 0) or 0
    norm["progressive_passes_p90"] = per_90(raw.get("progressive_passes", 0), mins)

    # --- Per-90 defensive ---
    norm["tackles_p90"]        = per_90(raw.get("tackles", 0), mins)
    norm["interceptions_p90"]  = per_90(raw.get("interceptions", 0), mins)
    norm["blocks_p90"]         = per_90(raw.get("blocks", 0), mins)
    norm["clearances_p90"]     = per_90(raw.get("clearances", 0), mins)

    # --- Dribbles / carries ---
    norm["dribbles_p90"]             = per_90(raw.get("dribbles_success", 0), mins)
    norm["progressive_carries_p90"]  = per_90(raw.get("progressive_carries", 0), mins)

    # --- Aerial win % (direct from CSV, already a %) ---
    norm["aerial_win_pct"] = raw.get("aerial_win_pct", 0) or 0

    # --- Discipline ---
    norm["fouls_drawn_p90"]     = per_90(raw.get("fouls_drawn", 0), mins)
    norm["fouls_committed_p90"] = per_90(raw.get("fouls_committed", 0), mins)
    norm["yellow_cards"]        = raw.get("yellow_cards", 0) or 0
    norm["red_cards"]           = raw.get("red_cards", 0) or 0

    # --- Extra metrics (available in 2024-25, used by scout) ---
    norm["sca90"]               = raw.get("sca90", 0) or 0
    norm["gca90"]               = raw.get("gca90", 0) or 0
    norm["npxg_p90"]            = per_90(raw.get("npxg", 0), mins)
    norm["xa_p90"]              = per_90(raw.get("xa", 0), mins)
    norm["passes_penalty_area_p90"] = per_90(raw.get("passes_penalty_area", 0), mins)
    norm["att_pen_touches_p90"] = per_90(raw.get("att_pen_touches", 0), mins)
    norm["tkl_pct"]             = raw.get("tkl_pct", 0) or 0

    # --- Understat xG chain metrics (now available 2021-22 onwards) ---
    norm["xg_chain_p90"]   = per_90(raw.get("xg_chain", 0), mins)
    norm["xg_buildup_p90"] = per_90(raw.get("xg_buildup", 0), mins)

    return norm
