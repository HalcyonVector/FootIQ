"""
Position-based metric config and composite scoring.
Uses only metrics available in the CSV dataset.
Dynamic filtering: only show metrics where the player actually has data.
"""

import math

# ─────────────────────────────────────────────────────────────────────────────
# Position detector
# ─────────────────────────────────────────────────────────────────────────────

def _detect_position(position_str: str) -> str:
    pos = (position_str or "").lower().strip()
    first = pos.split(",")[0].strip()
    if first == "fw":  return "attacker"
    if first == "mf":  return "midfielder"
    if first == "df":  return "defender"
    if first == "gk":  return "goalkeeper"
    if any(k in pos for k in ["attack", "forward", "winger", "striker"]): return "attacker"
    if "midfield" in pos: return "midfielder"
    if any(k in pos for k in ["defend", "back"]): return "defender"
    if any(k in pos for k in ["goal", "keeper"]): return "goalkeeper"
    return "attacker"

# ─────────────────────────────────────────────────────────────────────────────
# Master candidate metric lists per position (ordered by importance)
# These include ALL possible metrics. Dynamic filtering removes ones with no data.
# ─────────────────────────────────────────────────────────────────────────────

_MASTER_METRICS = {
    "attacker": [
        # (metric_key, label, max_val, weight)
        ("goals_p90",              "Goals p90",         1.00, 0.22),
        ("xg_p90",                 "xG p90",            0.90, 0.18),
        ("assists_p90",            "Assists p90",       0.50, 0.12),
        ("xag_p90",                "xAG p90",           0.55, 0.10),
        ("shots_on_p90",           "SOT p90",           2.00, 0.10),
        ("key_passes_p90",         "Key Passes p90",    2.57, 0.09),
        ("sca90",                  "SCA90",             7.0,  0.07),
        ("progressive_carries_p90","Prog Carries p90",  5.62, 0.05),
        ("dribbles_p90",           "Dribbles p90",      2.79, 0.04),
        ("aerial_win_pct",         "Aerial Win %",      75.0, 0.03),
    ],
    "midfielder": [
        ("key_passes_p90",         "Key Passes p90",    2.57, 0.16),
        ("pass_accuracy",          "Pass Acc %",        94.0, 0.14),
        ("progressive_passes_p90", "Prog Passes p90",   8.73, 0.13),
        ("assists_p90",            "Assists p90",       0.43, 0.12),
        ("xag_p90",                "xAG p90",           0.45, 0.10),
        ("sca90",                  "SCA90",             5.5,  0.09),
        ("xg_p90",                 "xG p90",            0.45, 0.08),
        ("tackles_p90",            "Tackles p90",       3.36, 0.08),
        ("progressive_carries_p90","Prog Carries p90",  5.62, 0.06),
        ("dribbles_p90",           "Dribbles p90",      2.79, 0.04),
    ],
    "defender": [
        ("tackles_p90",            "Tackles p90",       3.36, 0.22),
        ("interceptions_p90",      "Intercepts p90",    1.93, 0.18),
        ("clearances_p90",         "Clearances p90",    6.93, 0.14),
        ("aerial_win_pct",         "Aerial Win %",      80.0, 0.16),
        ("pass_accuracy",          "Pass Acc %",        94.0, 0.12),
        ("blocks_p90",             "Blocks p90",        2.00, 0.08),
        ("progressive_passes_p90", "Prog Passes p90",   8.73, 0.06),
        ("xag_p90",                "xAG p90",           0.20, 0.02),
        ("sca90",                  "SCA90",             3.0,  0.02),
    ],
    "goalkeeper": [
        ("pass_accuracy",          "Pass Acc %",        85.0, 0.50),
        ("aerial_win_pct",         "Aerial Win %",      75.0, 0.35),
        ("sca90",                  "SCA90",             2.0,  0.10),
        ("xag_p90",                "xAG p90",           0.10, 0.05),
    ],
}


def _build_cfg_from_available(position: str, norm: dict) -> dict:
    """Build a metric config using only metrics where the player has actual data (> 0)."""
    pos = _detect_position(position)
    candidates = _MASTER_METRICS.get(pos, _MASTER_METRICS["attacker"])
    keep = [(m, l, mx, w) for m, l, mx, w in candidates if (norm.get(m) or 0) > 0]
    if not keep:
        # Absolute fallback: just goals and assists
        keep = [("goals_p90", "Goals p90", 0.82, 0.60), ("assists_p90", "Assists p90", 0.43, 0.40)]
    metrics, labels, max_vals, weights = zip(*keep)
    return {
        "metrics":  list(metrics),
        "labels":   list(labels),
        "max_vals": list(max_vals),
        "weights":  list(weights),
    }


def get_season_metric_set(season: str, position: str = "attacker", norm: dict = None) -> dict:
    """Return a metric config for the solo player page.
    If norm is provided, dynamically filters to only metrics with actual data.
    """
    if norm is not None:
        return _build_cfg_from_available(position, norm)
    # Fallback: return full master list for the position (will be filtered later)
    pos = _detect_position(position)
    candidates = _MASTER_METRICS.get(pos, _MASTER_METRICS["attacker"])
    metrics, labels, max_vals, weights = zip(*candidates)
    return {"metrics": list(metrics), "labels": list(labels),
            "max_vals": list(max_vals), "weights": list(weights)}


# xG now available 2021-22 onwards (Understat merge filled the gaps)
_XG_SEASONS = {"2021-22", "2022-23", "2023-24", "2024-25"}


def get_comparison_metric_set(seasons: list, position: str = "attacker", norms: list = None) -> tuple:
    """Return (metric_config, mode_label) for a comparison.
    If norms provided, filters to metrics available for ALL players.
    All-2024-25 → modern; otherwise → universal.
    """
    pos = _detect_position(position)
    all_modern = all(s == "2024-25" for s in seasons)
    mode = "modern" if all_modern else "universal"

    if norms:
        # Find intersection of metrics available across all players
        available = None
        for norm in norms:
            cfg = _build_cfg_from_available(pos, norm)
            this_set = set(cfg["metrics"])
            available = this_set if available is None else available & this_set

        if not available:
            available = {"goals_p90", "assists_p90"}

        candidates = _MASTER_METRICS.get(pos, _MASTER_METRICS["attacker"])
        keep = [(m, l, mx, w) for m, l, mx, w in candidates if m in available]
        if not keep:
            keep = [("goals_p90", "Goals p90", 0.82, 0.60), ("assists_p90", "Assists p90", 0.43, 0.40)]
        metrics, labels, max_vals, weights = zip(*keep)
        cfg = {"metrics": list(metrics), "labels": list(labels),
               "max_vals": list(max_vals), "weights": list(weights)}
        return (cfg, mode)

    # No norms provided — return full master list
    candidates = _MASTER_METRICS.get(pos, _MASTER_METRICS["attacker"])
    metrics, labels, max_vals, weights = zip(*candidates)
    return ({"metrics": list(metrics), "labels": list(labels),
             "max_vals": list(max_vals), "weights": list(weights)}, mode)


def compute_composite_score_from_cfg(norm: dict, cfg: dict) -> float:
    """Compute composite score using only the metrics in the given cfg (available data only)."""
    total_weight = sum(cfg["weights"])
    if total_weight == 0:
        return 0.0
    score = 0.0
    for metric, weight, max_val in zip(cfg["metrics"], cfg["weights"], cfg["max_vals"]):
        val = norm.get(metric, 0) or 0
        ratio = min(val / max_val, 1.0) if max_val > 0 else 0.0
        score += ratio * (weight / total_weight)  # normalize weights to sum to 1
    return round(score * 100, 1)


# ─────────────────────────────────────────────────────────────────────────────
# Legacy configs (used by scout, similar players — unchanged)
# ─────────────────────────────────────────────────────────────────────────────

POSITION_CONFIG = {
    "attacker": {
        "metrics":  ["goals_p90", "assists_p90", "xg_p90", "shots_on_p90",
                     "key_passes_p90", "dribbles_p90", "progressive_carries_p90", "aerial_win_pct"],
        "weights":  [0.25, 0.15, 0.20, 0.10, 0.10, 0.08, 0.07, 0.05],
        "max_vals": [0.82, 0.43, 0.68, 1.45, 2.57, 2.79, 5.62, 75.0],
        "labels":   ["Goals p90", "Assists p90", "xG p90", "SOT p90",
                     "Key Passes p90", "Dribbles p90", "Prog Carries p90", "Aerial Win %"],
    },
    "midfielder": {
        "metrics":  ["key_passes_p90", "pass_accuracy", "progressive_passes_p90", "assists_p90",
                     "tackles_p90", "dribbles_p90", "xg_p90", "aerial_win_pct"],
        "weights":  [0.18, 0.18, 0.15, 0.14, 0.14, 0.09, 0.07, 0.05],
        "max_vals": [2.57, 94.0, 8.73, 0.43, 3.36, 2.79, 0.45, 70.0],
        "labels":   ["Key Passes p90", "Pass Acc %", "Prog Passes p90", "Assists p90",
                     "Tackles p90", "Dribbles p90", "xG p90", "Aerial Win %"],
    },
    "defender": {
        "metrics":  ["tackles_p90", "interceptions_p90", "blocks_p90", "aerial_win_pct",
                     "pass_accuracy", "progressive_passes_p90", "clearances_p90", "fouls_committed_p90"],
        "weights":  [0.22, 0.20, 0.12, 0.18, 0.12, 0.08, 0.05, 0.03],
        "max_vals": [3.36, 1.93, 2.00, 80.0, 94.0, 8.73, 6.93, 2.5],
        "labels":   ["Tackles p90", "Intercepts p90", "Blocks p90", "Aerial Win %",
                     "Pass Acc %", "Prog Passes p90", "Clearances p90", "Fouls Comm p90"],
    },
    "goalkeeper": {
        "metrics":  ["pass_accuracy", "aerial_win_pct", "fouls_committed_p90",
                     "goals_p90", "assists_p90", "key_passes_p90"],
        "weights":  [0.35, 0.25, 0.15, 0.10, 0.10, 0.05],
        "max_vals": [85.0, 75.0, 2.0, 0.1, 0.1, 0.5],
        "labels":   ["Pass Acc %", "Aerial Win %", "Fouls Comm p90",
                     "Goals Scored p90", "Assists p90", "Key Passes p90"],
    },
}

SCOUT_POSITION_CONFIG = {
    "attacker": {
        "metrics":  ["goals_p90", "xg_p90", "assists_p90", "shots_on_p90",
                     "sca90", "xa_p90", "dribbles_p90", "progressive_carries_p90",
                     "att_pen_touches_p90", "aerial_win_pct"],
        "weights":  [0.20, 0.18, 0.12, 0.10, 0.10, 0.10, 0.07, 0.06, 0.05, 0.02],
        "max_vals": [0.82, 0.68, 0.43, 1.45, 7.0, 0.45, 2.79, 5.62, 7.0, 75.0],
        "labels":   ["Goals p90", "xG p90", "Assists p90", "SOT p90",
                     "SCA90", "xA p90", "Dribbles p90", "Prog Carries p90",
                     "Att Pen Touches p90", "Aerial Win %"],
    },
    "midfielder": {
        "metrics":  ["key_passes_p90", "pass_accuracy", "progressive_passes_p90", "assists_p90",
                     "sca90", "xa_p90", "tackles_p90", "dribbles_p90",
                     "passes_penalty_area_p90", "aerial_win_pct"],
        "weights":  [0.15, 0.15, 0.13, 0.12, 0.10, 0.10, 0.12, 0.07, 0.04, 0.02],
        "max_vals": [2.57, 94.0, 8.73, 0.43, 5.5, 0.45, 3.36, 2.79, 2.0, 70.0],
        "labels":   ["Key Passes p90", "Pass Acc %", "Prog Passes p90", "Assists p90",
                     "SCA90", "xA p90", "Tackles p90", "Dribbles p90",
                     "Passes into Box p90", "Aerial Win %"],
    },
    "defender": {
        "metrics":  ["tackles_p90", "interceptions_p90", "blocks_p90", "aerial_win_pct",
                     "pass_accuracy", "progressive_passes_p90", "clearances_p90",
                     "tkl_pct", "fouls_committed_p90", "att_pen_touches_p90"],
        "weights":  [0.20, 0.18, 0.10, 0.18, 0.12, 0.08, 0.07, 0.05, 0.01, 0.01],
        "max_vals": [3.36, 1.93, 2.00, 80.0, 94.0, 8.73, 6.93, 85.0, 2.5, 1.5],
        "labels":   ["Tackles p90", "Intercepts p90", "Blocks p90", "Aerial Win %",
                     "Pass Acc %", "Prog Passes p90", "Clearances p90",
                     "Tackle %", "Fouls Comm p90", "Att Pen Touches p90"],
    },
    "goalkeeper": {
        "metrics":  ["pass_accuracy", "aerial_win_pct", "fouls_committed_p90",
                     "goals_p90", "assists_p90", "key_passes_p90"],
        "weights":  [0.35, 0.25, 0.15, 0.10, 0.10, 0.05],
        "max_vals": [85.0, 75.0, 2.0, 0.1, 0.1, 0.5],
        "labels":   ["Pass Acc %", "Aerial Win %", "Fouls Comm p90",
                     "Goals Scored p90", "Assists p90", "Key Passes p90"],
    },
}


def get_scout_position_config(position_str: str) -> dict:
    return SCOUT_POSITION_CONFIG[_detect_position(position_str)]


def get_position_config(position_str: str) -> dict:
    return POSITION_CONFIG[_detect_position(position_str)]


def get_radar_data(norm: dict, config: dict = None) -> tuple:
    if config is None:
        config = get_position_config(norm.get("position", "Attacker"))
    labels  = config["labels"]
    metrics = config["metrics"]
    maxvals = config["max_vals"]
    raw     = [norm.get(m, 0) or 0 for m in metrics]
    scaled  = [min(v / mx, 1.0) if mx > 0 else 0.0 for v, mx in zip(raw, maxvals)]
    return labels, raw, scaled


def compute_composite_score(norm: dict) -> float:
    """Legacy composite score using position config (for profile header display)."""
    config = get_position_config(norm.get("position", "Attacker"))
    score  = 0.0
    for metric, weight, max_val in zip(config["metrics"], config["weights"], config["max_vals"]):
        val   = norm.get(metric, 0) or 0
        ratio = min(val / max_val, 1.0) if max_val > 0 else 0.0
        score += ratio * weight
    return round(score * 100, 1)


def compute_similarity(scaled_target: list, scaled_candidate: list) -> float:
    if not scaled_target or not scaled_candidate or len(scaled_target) != len(scaled_candidate):
        return 0.0
    dist = math.sqrt(sum((t - c) ** 2 for t, c in zip(scaled_target, scaled_candidate)))
    max_dist = math.sqrt(len(scaled_target))
    sim = max(0.0, 1.0 - (dist / max_dist))
    return round(sim * 100, 1)


def get_archetype_scores(norm: dict) -> dict:
    """
    Compute five archetype dimension scores in [0, 1].

    Each bucket uses metrics that are reliably populated across the dataset.
    Normalization maxes are set to ~90th-percentile values so most players
    land in a meaningful range rather than clustering at 0 or 1.
    """
    # ── Attack: goal threat ──────────────────────────────────────────────────
    goals   = (norm.get("goals_p90",    0) or 0)
    xg      = (norm.get("xg_p90",       0) or 0)
    sot     = (norm.get("shots_on_p90", 0) or 0)
    attack  = (goals * 0.45 + xg * 0.35 + sot * 0.20) / 0.65   # max ≈ 0.65

    # ── Creation: chance creation ────────────────────────────────────────────
    kp      = (norm.get("key_passes_p90", 0) or 0)
    ast     = (norm.get("assists_p90",    0) or 0)
    xag     = (norm.get("xag_p90",        0) or 0)
    sca     = (norm.get("sca90",          0) or 0)
    creation = (kp * 0.30 + ast * 0.25 + xag * 0.25 + sca * 0.20) / 1.80  # max ≈ 1.80

    # ── Progression: ball advancement ───────────────────────────────────────
    prog_c  = (norm.get("progressive_carries_p90", 0) or 0)
    prog_p  = (norm.get("progressive_passes_p90",  0) or 0)
    drib    = (norm.get("dribbles_p90",             0) or 0)
    progression = (prog_c * 0.40 + prog_p * 0.35 + drib * 0.25) / 5.50  # max ≈ 5.50

    # ── Technical: ball control & duels ─────────────────────────────────────
    pass_acc = (norm.get("pass_accuracy", 0) or 0) / 100.0   # normalise % → [0,1]
    drib2    = (norm.get("dribbles_p90",  0) or 0)
    aerial   = (norm.get("aerial_win_pct",0) or 0) / 100.0
    technical = (pass_acc * 0.50 + (drib2 / 3.0) * 0.30 + aerial * 0.20)  # max ≈ 1.0

    # ── Defense: defensive actions ───────────────────────────────────────────
    tkl     = (norm.get("tackles_p90",       0) or 0)
    inter   = (norm.get("interceptions_p90", 0) or 0)
    clr     = (norm.get("clearances_p90",    0) or 0)
    blk     = (norm.get("blocks_p90",        0) or 0)
    defense = (tkl * 0.35 + inter * 0.30 + clr * 0.20 + blk * 0.15) / 2.80  # max ≈ 2.80

    return {
        "Attack":      round(min(max(attack,      0.0), 1.0), 4),
        "Creation":    round(min(max(creation,    0.0), 1.0), 4),
        "Progression": round(min(max(progression, 0.0), 1.0), 4),
        "Technical":   round(min(max(technical,   0.0), 1.0), 4),
        "Defense":     round(min(max(defense,     0.0), 1.0), 4),
    }
