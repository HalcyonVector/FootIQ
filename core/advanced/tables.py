"""
League tables and team pages, derived from the per-player match rows
(player_matches) -- every row already carries the match score, so a table
needs no extra data: collapse to one row per (match, team), then add up.

xG for/against comes from summing each side's player xG per match (the
opponent's xG in the same match is a team's xG against).

All of this works on ONE league-season partition (a few thousand rows).
"""

import numpy as np
import pandas as pd

FORM_LEN = 5


def _team_matches(rows: pd.DataFrame) -> pd.DataFrame:
    """One row per (match, team): date, opponent, venue, score, team xG, plus
    the opponent's xG in that match."""
    if rows.empty:
        return rows
    g = rows.groupby(["match_key", "team"], sort=False)
    tm = g.agg(date=("date", "first"), opp=("opp", "first"), home=("home", "first"),
               gf=("gf", "first"), ga=("ga", "first"), xgf=("xg", "sum")).reset_index()
    opp_xg = tm[["match_key", "team", "xgf"]].rename(columns={"team": "opp", "xgf": "xga"})
    tm = tm.merge(opp_xg, on=["match_key", "opp"], how="left")
    tm = tm.dropna(subset=["gf", "ga"])
    tm["gf"] = tm["gf"].astype(int)
    tm["ga"] = tm["ga"].astype(int)
    tm["result"] = np.where(tm["gf"] > tm["ga"], "W", np.where(tm["gf"] < tm["ga"], "L", "D"))
    return tm.sort_values(["date", "match_key"], kind="stable")


def _record(tm: pd.DataFrame) -> dict:
    w = int((tm["result"] == "W").sum())
    d = int((tm["result"] == "D").sum())
    l = int((tm["result"] == "L").sum())
    gf, ga = int(tm["gf"].sum()), int(tm["ga"].sum())
    return {
        "played": len(tm), "won": w, "drawn": d, "lost": l, "gf": gf, "ga": ga, "gd": gf - ga,
        "points": 3 * w + d,
        "xgf": round(float(tm["xgf"].sum()), 1), "xga": round(float(tm["xga"].fillna(0).sum()), 1),
        "form": tm["result"].tail(FORM_LEN).tolist(),
    }


def league_table(rows: pd.DataFrame) -> list[dict]:
    """Standings sorted by points, goal difference, goals for."""
    tm = _team_matches(rows)
    if tm.empty:
        return []
    table = [{"team": team, **_record(g)} for team, g in tm.groupby("team", sort=False)]
    table.sort(key=lambda r: (-r["points"], -r["gd"], -r["gf"], r["team"]))
    for i, r in enumerate(table, 1):
        r["pos"] = i
    return table


def team_page(rows: pd.DataFrame, team: str, names: dict[int, str]) -> dict | None:
    """Results, record and squad table for one team. `names` maps
    whoscored_player_id -> display name."""
    tm = _team_matches(rows)
    mine = tm[tm["team"] == team]
    if mine.empty:
        return None

    results = [{
        "date": r.date, "opp": r.opp, "home": bool(r.home), "gf": r.gf, "ga": r.ga, "result": r.result,
        "xgf": round(float(r.xgf), 2), "xga": None if pd.isna(r.xga) else round(float(r.xga), 2),
    } for r in mine.itertuples(index=False)]

    squad = []
    for pid, g in rows[rows["team"] == team].groupby("whoscored_player_id"):
        rated = g["rating"].dropna()
        pos = g["pos"].dropna()
        squad.append({
            "player_id": int(pid), "name": names.get(int(pid)) or f"Player {int(pid)}",
            "position": pos.mode().iloc[0] if len(pos) else None,
            "apps": len(g), "starts": int(g["started"].sum()), "minutes": int(round(g["minutes"].sum())),
            "goals": int(g["goals"].sum()), "assists": int(g["assists"].sum()),
            "xg": round(float(g["xg"].sum()), 1), "xa": round(float(g["xa"].sum()), 1),
            "rating": round(float(rated.mean()), 2) if len(rated) else None,
            "yellow": int(g["yellow"].sum()), "red": int(g["red"].sum()),
        })
    squad.sort(key=lambda p: -p["minutes"])

    table = league_table(rows)
    standing = next((r for r in table if r["team"] == team), None)
    return {"team": team, "record": _record(mine), "pos": standing["pos"] if standing else None,
            "teams": len(table), "results": results, "squad": squad}
