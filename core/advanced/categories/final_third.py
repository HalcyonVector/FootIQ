"""
Final Third — four pillars (Shooting/Link-Up/Carrying/Ball-Winning), each
scored two ways: "floor" (volume-scaled raw output) and "per-touch" (value
per final-third touch). The floor/per-touch RAW values computed here are
percentile-ranked against the cohort at request time (see
core/advanced/percentiles.py::build_final_third_scores) to produce:
  - Completeness: geometric mean of the 4 pillars' floor percentiles,
    penalized by their spread — a weak pillar can't be bought back by the
    other three, so high scores are rare by construction.
  - Impact: mean of the per-touch percentiles for the player's 2 STRONGEST
    pillars only — rewards a specialist without punishing them for not
    doing everything.
This module only computes the raw pillar inputs; the percentile math lives
in percentiles.py since it needs the full cohort, not just one player.
"""

from core.advanced import geometry as g, qualifiers as q
from core.advanced.accumulate import PlayerAcc

FINAL_THIRD_X = 200 / 3

# Raw counters that feed the 4 pillars — converted to per-90 by the aggregator.
P90_KEYS = {
    "ft_touches", "ft_shots", "ft_goals", "ft_sot", "ft_passes", "ft_key_passes",
    "ft_assists", "ft_carries", "ft_prog_carries", "ft_carries_into_box", "ft_def_actions_high",
}


def compute_final_third(events: list[dict], carries: list[dict]) -> dict:
    acc = PlayerAcc()

    for e in events:
        pid = e.get("player_id")
        x = e.get("x")
        if pid is None or x is None or x < FINAL_THIRD_X:
            continue
        etype = e["type"]

        if e.get("is_touch"):
            acc.add(pid, "ft_touches")

        if etype in ("MissedShots", "SavedShot", "Goal", "ShotOnPost"):
            qm = q.qmap(e["qualifiers"])
            if q.has_qualifier(qm, q.OWN_GOAL_Q):
                continue
            acc.add(pid, "ft_shots")
            if etype == "Goal":
                acc.add(pid, "ft_goals")
            if etype in ("Goal", "SavedShot"):
                acc.add(pid, "ft_sot")

        elif etype == "Pass":
            qm = q.qmap(e["qualifiers"])
            if not q.is_open_play(qm):
                continue
            if e["outcome_type"] == "Successful":
                acc.add(pid, "ft_passes")
                if q.has_qualifier(qm, q.KEY_PASS_Q):
                    acc.add(pid, "ft_key_passes")
                if q.has_qualifier(qm, q.ASSIST_Q):
                    acc.add(pid, "ft_assists")

        elif etype == "Tackle" and e["outcome_type"] == "Successful":
            acc.add(pid, "ft_def_actions_high")
        elif etype in ("Interception", "BallRecovery"):
            acc.add(pid, "ft_def_actions_high")

    for c in carries:
        if c["start_x"] < FINAL_THIRD_X:
            continue
        acc.add(c["player_id"], "ft_carries")
        start, end = (c["start_x"], c["start_y"]), (c["end_x"], c["end_y"])
        if g.is_progressive_action(start, end):
            acc.add(c["player_id"], "ft_prog_carries")
        if g.in_box(*end):
            acc.add(c["player_id"], "ft_carries_into_box")

    return acc.to_dict()


def finalize_final_third(totals: dict) -> dict:
    """Raw counts pass through unchanged (per-90 conversion + pillar
    percentile-ranking both happen downstream)."""
    out = {}
    for pid, t in totals.items():
        out[pid] = {k: t.get(k, 0) for k in P90_KEYS}
    return out


def pillar_floor_scores(row: dict) -> dict:
    """Raw (un-normalized) floor score per pillar from a player-season's
    already-per-90'd ft_* columns. Simple volume+quality blends — the exact
    weights are a judgment call, not a literal spec; percentile-ranking
    against the cohort (in percentiles.py) is what actually makes these
    comparable, not the absolute numbers."""
    g_ = lambda k: row.get(k) or 0
    return {
        "shooting": g_("ft_goals_p90") * 4 + g_("ft_sot_p90") * 2 + g_("ft_shots_p90"),
        "linkup": g_("ft_passes_p90") * (g_("pass_accuracy_pct") / 100 if row.get("pass_accuracy_pct") else 0.5)
                  + g_("ft_key_passes_p90") * 3 + g_("ft_assists_p90") * 5,
        "carrying": g_("ft_carries_p90") + g_("ft_prog_carries_p90") * 2 + g_("ft_carries_into_box_p90") * 3,
        "ballwinning": g_("ft_def_actions_high_p90") * 2,
    }


def pillar_per_touch_scores(row: dict) -> dict:
    touches = row.get("ft_touches_p90") or 0
    if touches <= 0:
        return {k: 0 for k in ("shooting", "linkup", "carrying", "ballwinning")}
    floor = pillar_floor_scores(row)
    return {k: v / touches for k, v in floor.items()}
