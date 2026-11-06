"""
Per-match extraction for the player "Overview" (the stat line, form chart,
shot map, xG and heatmaps that paid sites lead with).

One call per match returns three things, all derived straight from the raw
WhoScored match JSON:

  - player_rows : one row per player who played, with that match's counting
                  stats (goals, assists, cards, rating, passes, tackles...).
  - shot_rows   : one row per shot, with every flag the xG model needs plus
                  the passer who set it up (for xA).
  - heat        : per-player touch / defensive-action counts binned onto a
                  GRID_X x GRID_Y pitch grid (a heatmap is just this array;
                  storing the grid instead of raw touches keeps it ~1KB per
                  player-season rather than ~1500 rows).

xG itself is NOT computed here -- it needs the model fitted on every shot
first, which the build script does in a second pass (see
scraping/build_overview_data.py). Nothing here is read at request time.
"""

import numpy as np

from core.advanced import qualifiers as q

GRID_X, GRID_Y = 24, 16

SHOT_TYPES = {"Goal", "MissedShots", "SavedShot", "ShotOnPost"}
DEFENSIVE_TYPES = {"Tackle", "Interception", "Clearance", "BallRecovery", "BlockedPass"}
RED_CARDS = {"Red", "SecondYellow"}

# Counting stats WhoScored already tallies per minute in each player's own
# `stats` block. Summing those dicts gives the same numbers its site shows,
# so we read them rather than re-deriving from raw events.
_STAT_SUMS = {
    "passes": "passesTotal",
    "passes_acc": "passesAccurate",
    "key_passes": "passesKey",
    "touches": "touches",
    "tackles": "tacklesTotal",
    "tackles_won": "tackleSuccessful",
    "interceptions": "interceptions",
    "clearances": "clearances",
    "aerials": "aerialsTotal",
    "aerials_won": "aerialsWon",
    "dribbles": "dribblesAttempted",
    "dribbles_won": "dribblesWon",
    "fouls": "foulsCommited",
    "saves": "totalSaves",
}


def _sum_dict(d) -> int:
    if not isinstance(d, dict):
        return 0
    try:
        return int(sum(d.values()))
    except (TypeError, ValueError):
        return 0


def _final_rating(stats: dict):
    r = stats.get("ratings")
    if not isinstance(r, dict) or not r:
        return None
    try:
        last = max(r, key=lambda k: int(k))
        return round(float(r[last]), 2)
    except (TypeError, ValueError):
        return None


def _cell(x: float, y: float) -> int:
    ix = min(max(int(x / 100.0 * GRID_X), 0), GRID_X - 1)
    iy = min(max(int(y / 100.0 * GRID_Y), 0), GRID_Y - 1)
    return ix * GRID_Y + iy


def _situation(qm: dict) -> str:
    if "Penalty" in qm:
        return "penalty"
    if "FreekickTaken" in qm:
        return "free_kick"
    if "FromCorner" in qm or "CornerTaken" in qm:
        return "corner"
    if not q.is_open_play(qm):
        return "set_piece"
    return "open_play"


def _shot_rows(match_key: str, events: list[dict], by_seq: dict) -> list[dict]:
    rows = []
    for e in events:
        if e["type"] not in SHOT_TYPES or e.get("period") == "PenaltyShootout":
            continue
        pid, x, y = e.get("player_id"), e.get("x"), e.get("y")
        if pid is None or x is None or y is None:
            continue
        qm = q.qmap(e["qualifiers"])
        if q.OWN_GOAL_Q in qm:
            continue

        # Who played the pass that led to this shot. RelatedEventId points
        # at the *other* event's per-match seq id; only trust it when it
        # really is a teammate's pass (it can point at fouls etc. otherwise).
        assist_pid = None
        if "Assisted" in qm and qm.get("RelatedEventId"):
            try:
                cand = by_seq.get((e["team_id"], int(qm["RelatedEventId"])))
            except (TypeError, ValueError):
                cand = None
            if cand and cand["type"] == "Pass" and cand["team_id"] == e["team_id"] \
                    and cand.get("player_id") not in (None, pid):
                assist_pid = cand["player_id"]

        if e["type"] == "Goal":
            outcome = "goal"
        elif e["type"] == "ShotOnPost":
            outcome = "post"
        elif e["type"] == "SavedShot":
            outcome = "blocked" if "Blocked" in qm else "saved"
        else:
            outcome = "off_target"

        bp = q.body_part(qm)
        situation = _situation(qm)
        gm_y, gm_z = q.qualifier_float(qm, "GoalMouthY"), q.qualifier_float(qm, "GoalMouthZ")
        rows.append({
            "match_key": match_key,
            "whoscored_player_id": pid,
            "assist_pid": assist_pid,
            "minute": e.get("minute"),
            "x": round(float(x), 1), "y": round(float(y), 1),
            "outcome": outcome,
            "situation": situation,
            "body": "head" if bp == "Head" else ("foot" if bp in ("RightFoot", "LeftFoot") else "other"),
            "big_chance": "BigChance" in qm,
            "gm_y": gm_y, "gm_z": gm_z,
            # model flags
            "f_head": bp == "Head",
            "f_other_body": bp == "OtherBodyPart",
            "f_direct_fk": situation == "free_kick",
            "f_corner": situation == "corner",
            "f_other_sp": situation == "set_piece",
            "f_fast_break": "FastBreak" in qm,
            "f_assisted": "Assisted" in qm,
        })
    return rows


def extract_match(match_key: str, mj: dict, events: list[dict], minutes: dict):
    """-> (player_rows, shot_rows, heat) for one match. `minutes` is
    minutes.compute_minutes_played()'s {player_id: minutes}."""
    # eventId is a per-TEAM counter, not per-match: the same number exists
    # once for each side, so a lookup must be keyed by (team_id, seq_id).
    by_seq = {(e["team_id"], e["seq_id"]): e for e in events if e.get("seq_id") is not None}
    shots = _shot_rows(match_key, events, by_seq)

    goals, pens, assists, yellow, red, shot_n, sot = {}, {}, {}, {}, {}, {}, {}
    for s in shots:
        pid = s["whoscored_player_id"]
        shot_n[pid] = shot_n.get(pid, 0) + 1
        if s["outcome"] in ("goal", "saved"):
            sot[pid] = sot.get(pid, 0) + 1
        if s["outcome"] == "goal":
            goals[pid] = goals.get(pid, 0) + 1
            if s["situation"] == "penalty":
                pens[pid] = pens.get(pid, 0) + 1
            if s["assist_pid"] is not None:
                assists[s["assist_pid"]] = assists.get(s["assist_pid"], 0) + 1
    for e in events:
        if e["type"] == "Card" and e.get("player_id") is not None:
            if e.get("card_type") == "Yellow":
                yellow[e["player_id"]] = yellow.get(e["player_id"], 0) + 1
            elif e.get("card_type") in RED_CARDS:
                red[e["player_id"]] = red.get(e["player_id"], 0) + 1

    # Heat grids: touches and defensive actions per player.
    heat: dict = {}
    for e in events:
        pid, x, y = e.get("player_id"), e.get("x"), e.get("y")
        if pid is None or x is None or y is None or minutes.get(pid, 0) <= 0:
            continue
        is_touch = e.get("is_touch")
        is_def = e["type"] in DEFENSIVE_TYPES
        if not (is_touch or is_def):
            continue
        h = heat.get(pid)
        if h is None:
            h = heat[pid] = (np.zeros(GRID_X * GRID_Y, dtype=np.uint16),
                             np.zeros(GRID_X * GRID_Y, dtype=np.uint16))
        c = _cell(x, y)
        if is_touch:
            h[0][c] += 1
        if is_def:
            h[1][c] += 1

    try:
        gf_home, gf_away = (int(s) for s in str(mj.get("score", "")).replace(" ", "").split(":"))
    except ValueError:
        gf_home = gf_away = None
    date = str(mj.get("startTime") or "")[:10]

    player_rows = []
    for side, other in (("home", "away"), ("away", "home")):
        team, opp = mj.get(side) or {}, mj.get(other) or {}
        gf, ga = (gf_home, gf_away) if side == "home" else (gf_away, gf_home)
        for p in team.get("players", []):
            pid = p.get("playerId")
            mins = minutes.get(pid, 0.0)
            if pid is None or mins <= 0:
                continue
            stats = p.get("stats") or {}
            row = {
                "whoscored_player_id": pid,
                "match_key": match_key,
                "date": date,
                "team": team.get("name"),
                "opp": opp.get("name"),
                "home": side == "home",
                "gf": gf, "ga": ga,
                "started": bool(p.get("isFirstEleven")),
                "minutes": round(float(mins), 1),
                "pos": p.get("position"),
                "rating": _final_rating(stats),
                "motm": bool(p.get("isManOfTheMatch")),
                "goals": goals.get(pid, 0),
                "pens_scored": pens.get(pid, 0),
                "assists": assists.get(pid, 0),
                "yellow": yellow.get(pid, 0),
                "red": red.get(pid, 0),
                "shots": shot_n.get(pid, 0),
                "sot": sot.get(pid, 0),
            }
            for out_key, src in _STAT_SUMS.items():
                row[out_key] = _sum_dict(stats.get(src))
            player_rows.append(row)

    return player_rows, shots, heat
