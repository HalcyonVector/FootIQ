"""
Quadrant plots: two football questions on one chart, so the four corners are four player types
(for example "ball winning" against "carrying": who does both, who does one, who does neither).

Each axis is an INDEX from 0 to 100: the average percentile rank, within the players being
plotted, of a few related per-90 metrics (an axis can also be a single metric). Averaging
several metrics keeps one noisy number from deciding where a player lands, and the 50 line is
the median player on that axis, which is where the quadrant lines are drawn.

Adding a plot is adding one entry to PRESETS: the columns must exist in the advanced table
(tests/test_quadrants.py checks that), and the four names describe the corners.
"""

import pandas as pd

from core.advanced import config
from core.advanced.lookup import _clean_minutes
from core.advanced.metrics_master import INVERTED_METRICS


def _axis(label, *cols):
    return {"label": label, "cols": list(cols)}


# "positions" is the group a plot shows by default: a position group, or "attacking" = forwards plus
# attacking midfielders and wingers (wingers sit in the midfielder group in this app).
# tr = high on both axes, tl = high y only, br = high x only, bl = low on both.
PRESETS = [
    {"id": "winning_carrying", "title": "Ball winning vs carrying", "positions": "midfielder",
     "question": "Who wins the ball back, who drives it forward, and who does both?",
     "x": _axis("Carrying", "carry_prog_count_p90", "carry_penetration_gain_m_p90", "carry_into_box_count_p90",
                "carry_distance_sum_m_p90"),
     "y": _axis("Ball winning", "def_tackles_total_p90", "def_interceptions_total_p90", "def_recoveries_total_p90"),
     "quad": {"tr": "Win it and drive it", "tl": "Ball winners", "br": "Ball carriers", "bl": "Low involvement"}},
    {"id": "creation_threat", "title": "Chance creation vs shot threat", "positions": "attacking",
     "question": "Who makes chances for others and who takes them, and who does both?",
     "x": _axis("Shot threat", "shoot_xg_p90", "shoot_in_box_count_p90"),
     "y": _axis("Chance creation", "pass_xa_p90", "pass_key_passes_count_p90", "dm_shot_creator_p90"),
     "quad": {"tr": "Complete attackers", "tl": "Creators", "br": "Shooters", "bl": "Limited output"}},
    {"id": "passing_carrying", "title": "Progress by passing vs by carrying", "positions": "midfielder",
     "question": "Does a player move the team forward with the ball at his feet or with his passing?",
     "x": _axis("Carrying progression", "carry_prog_count_p90", "carry_penetration_gain_m_p90"),
     "y": _axis("Passing progression", "pass_prog_count_p90", "pass_penetration_gain_m_p90", "pass_progression_rate_pct"),
     "quad": {"tr": "Progress both ways", "tl": "Progress by passing", "br": "Progress by carrying", "bl": "Recyclers"}},
    {"id": "security_ambition", "title": "Ball security vs ambition", "positions": "midfielder",
     "question": "Who keeps the ball and who tries to break lines, and who does both?",
     "x": _axis("Ball security (pass accuracy)", "pass_accuracy_pct"),
     "y": _axis("Ambition (progression rate)", "pass_progression_rate_pct"),
     "quad": {"tr": "Safe and ambitious", "tl": "Ambitious, riskier", "br": "Safe recyclers", "bl": "Neither"}},
    {"id": "dribble_volume_success", "title": "Dribbling: volume vs success", "positions": "attacking",
     "question": "Who takes defenders on often, and who actually beats them?",
     "x": _axis("Take-ons attempted", "carry_takeons_attempted_p90"),
     "y": _axis("Take-on success", "carry_takeon_success_pct"),
     "quad": {"tr": "Elite dribblers", "tl": "Selective, efficient", "br": "Volume, wasteful", "bl": "Rarely dribble"}},
    {"id": "tackle_volume_success", "title": "Tackling: volume vs success", "positions": "defender",
     "question": "Who gets stuck in, and who wins the duels they take on?",
     "x": _axis("Tackles attempted", "def_tackles_total_p90"),
     "y": _axis("Tackle success", "def_tackle_success_pct"),
     "quad": {"tr": "Dominant tacklers", "tl": "Selective, precise", "br": "Busy, beaten", "bl": "Passive"}},
    {"id": "aerial", "title": "Aerial duels: volume vs quality", "positions": "defender",
     "question": "Who is involved in the air, and who wins it cleanly?",
     "x": _axis("Aerial duels", "aer_duels_count_p90"),
     "y": _axis("Duel quality", "aer_duel_quality_pct"),
     "quad": {"tr": "Aerial dominators", "tl": "Selective winners", "br": "Contest, lose", "bl": "Stay on the ground"}},
    {"id": "after_winning", "title": "After winning the ball", "positions": "midfielder",
     "question": "Who wins the ball back, and who turns it into progress straight away?",
     "x": _axis("Recoveries", "pr_recoveries_p90"),
     "y": _axis("Progress off recovery", "pr_prog_passes_off_recovery_p90", "pr_prog_carries_off_recovery_p90"),
     "quad": {"tr": "Win it and attack", "tl": "Opportunistic", "br": "Win it, recycle it", "bl": "Quiet in transition"}},
    {"id": "tempo", "title": "Tempo: accelerate vs settle", "positions": "midfielder",
     "question": "Who speeds the game up and who calms it down?",
     "x": _axis("Settling (resets)", "tempo_resets_p90"),
     "y": _axis("Accelerating (injectors)", "tempo_injectors_p90"),
     "quad": {"tr": "Two-way controllers", "tl": "Accelerators", "br": "Settlers", "bl": "Low tempo influence"}},
    {"id": "gk_style", "title": "Goalkeepers: shot stopping vs distribution", "positions": "goalkeeper",
     "question": "Who stops the shots, and who starts the attacks?",
     "x": _axis("Distribution accuracy", "gk_distribution_accuracy_pct"),
     "y": _axis("Save rate", "gk_save_rate_pct"),
     "quad": {"tr": "Complete keepers", "tl": "Shot stoppers", "br": "Distributors", "bl": "Below average on both"}},
]
BY_ID = {p["id"]: p for p in PRESETS}
# Columns a plot uses that the Explore metric picker does not list (so they have no label there).
EXTRA_LABELS = {"carry_distance_sum_m_p90": {"label": "Carry distance", "unit": "m"}}


def public_presets() -> list[dict]:
    """What the page needs to build its picker (no columns)."""
    return [{"id": p["id"], "title": p["title"], "question": p["question"], "positions": p["positions"],
             "x": p["x"]["label"], "y": p["y"]["label"], "quad": p["quad"]} for p in PRESETS]


def _index(subset: pd.DataFrame, cols: list[str]) -> pd.Series:
    """Mean percentile rank (0-100, higher is better) of the metrics over the given players."""
    ranks = []
    for col in cols:
        pct = subset[col].rank(pct=True, ascending=col not in INVERTED_METRICS) * 100
        ranks.append(pct)
    return sum(ranks) / len(ranks)


def quadrant_points(df: pd.DataFrame, preset_id: str, season: str, league: str | None = None,
                    position_group: str | None = None, min_minutes: int | None = None, limit: int = 2500) -> dict:
    """{"preset": ..., "points": [...]} for one preset under the same filters as the other Explore views.
    Position 'all' means the preset's own position group, so a goalkeeper never appears among outfielders."""
    preset = BY_ID[preset_id]
    cols = preset["x"]["cols"] + preset["y"]["cols"]
    subset = df[df["season"] == season]
    if league and league != "all":
        subset = subset[subset["league"] == league]
    group = preset["positions"] if not position_group or position_group == "all" else position_group
    if group == "attacking":
        subset = subset[(subset["_pos_group"] == "attacker") | subset["position"].astype(str).str.match(r"^(AM|FW|ML|MR)")]
    else:
        subset = subset[subset["_pos_group"] == group]
    floor = min_minutes if min_minutes is not None else config.minutes_floor(subset)
    subset = subset[subset["total_minutes"] >= floor]
    if any(c not in subset.columns for c in cols):
        return {"preset": preset, "points": []}
    subset = subset[subset[cols].notna().all(axis=1)]
    if subset.empty:
        return {"preset": preset, "points": []}
    subset = subset.sort_values("total_minutes", ascending=False).head(limit).copy()
    subset["_x"] = _index(subset, preset["x"]["cols"])
    subset["_y"] = _index(subset, preset["y"]["cols"])
    points = []
    for _, r in subset.iterrows():
        points.append({"x": float(r["_x"]), "y": float(r["_y"]), "name": r["player_name"], "team": r["team_name"],
                       "league": r["league"], "season": season, "group": r["_pos_group"],
                       "id": int(r["whoscored_player_id"]), "minutes": _clean_minutes(r["total_minutes"]),
                       "raw": [float(r[c]) for c in cols]})
    return {"preset": preset, "points": points}
