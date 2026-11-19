"""
How each team plays, per competition-season: possession, pressing, how high it wins the ball,
how direct its passing is, where it plays, and its attacking and defensive output. Each value is
ranked among the teams of the same competition-season.

Two sources, both already in the dataset:

* the per-match player rows (player_matches): added up per (match, team), with the opponent's
  totals from the other side of the same match. Possession, pressing, pass accuracy, shots, xG,
  aerial duels and take-ons come from here.
* the per-player event coordinates (chart_events, passing and defending), joined to each player's
  team for that season. Pass length, directness, final-third share and defensive height come
  from here. These are stored per player-season, not per match, so a player who changed clubs
  inside the season counts towards the team in their player-season row.

Event data has no tracking, so possession is a passing share and pressing is passes allowed per
defensive action over the whole pitch (the published PPDA counts only the opponent's half).
Pitch coordinates are 0-100 along each axis; distances use a 105 x 68 m pitch.
"""
from __future__ import annotations

import math

PITCH_X, PITCH_Y = 105.0, 68.0
FINAL_THIRD_X = 200 / 3            # x >= 66.7 on the 0-100 scale

# key, label, unit, decimals, rank order ("high" = biggest value ranks 1st), what it means
METRICS = [
    ("possession", "Possession", "%", 1, "high", "Share of the passes in its matches. Passes stand in for time on the ball."),
    ("pass_accuracy", "Pass accuracy", "%", 1, "high", "Completed passes as a share of all passes."),
    ("ppda", "Pressing (passes allowed per defensive action)", "", 1, "low",
     "Opponent passes for each of the team's tackles, interceptions and fouls, over the whole pitch. Lower means more pressing."),
    ("def_height", "Ball-winning height", "m", 1, "high",
     "Average distance from its own goal of the tackles, interceptions and recoveries its players make. Higher means it wins the ball further up."),
    ("directness", "Directness", "%", 1, "high", "Share of its passes that are progressive (move the ball a good distance towards goal)."),
    ("pass_length", "Average pass length", "m", 1, "high", "Average length of its passes."),
    ("final_third", "Passes in the final third", "%", 1, "high", "Share of its passes played in the attacking third."),
    ("shots", "Shots per match", "", 1, "high", "Shots per match."),
    ("xg", "xG per match", "", 2, "high", "Expected goals per match, from our own model."),
    ("xga", "xG against per match", "", 2, "low", "Expected goals conceded per match. Lower is better."),
    ("xg_per_shot", "xG per shot", "", 2, "high", "Average quality of its chances."),
    ("aerial_win", "Aerial duels won", "%", 1, "high", "Share of its aerial duels won."),
    ("takeons", "Take-ons per match", "", 1, "high", "Attempted dribbles past an opponent per match."),
]
META = [{"key": k, "label": l, "unit": u, "decimals": d, "order": o, "desc": desc} for k, l, u, d, o, desc in METRICS]


def _safe_div(a, b):
    return float(a) / float(b) if b else None


def compute(league: str, season: str, matches=None, players=None, passes=None, defs=None) -> list[dict]:
    """[{team, matches, values: {key: value}}] for one competition-season. The four tables can be
    passed in (tests do); otherwise they are read from the stored dataset."""
    import pandas as pd
    from core.advanced import store

    if matches is None:
        matches = store.get_season_matches(league, season)
    if matches is None or matches.empty:
        return []
    num = ["passes", "passes_acc", "tackles", "interceptions", "fouls", "shots", "xg", "aerials", "aerials_won", "dribbles"]
    m = matches.copy()
    for c in num:
        m[c] = pd.to_numeric(m.get(c), errors="coerce").fillna(0)
    tm = m.groupby(["match_key", "team"], sort=False).agg(opp=("opp", "first"), **{c: (c, "sum") for c in num}).reset_index()
    opp = tm[["match_key", "team", "passes", "xg"]].rename(columns={"team": "opp", "passes": "opp_passes", "xg": "opp_xg"})
    tm = tm.merge(opp, on=["match_key", "opp"], how="left")
    tm["poss"] = tm["passes"] / (tm["passes"] + tm["opp_passes"])

    # event coordinates, joined to the player's team for this season
    if players is None:
        df = store.get_advanced_df()
        players = df[(df["league"] == league) & (df["season"] == season)][["whoscored_player_id", "team_name"]]
    team_of = dict(zip(players["whoscored_player_id"].astype("int64"), players["team_name"]))
    if passes is None:
        passes = store.get_chart_partition("passing", league, season,
                                           ["whoscored_player_id", "x", "y", "end_x", "end_y", "progressive", "completed", "into_box"])
    if defs is None:
        defs = store.get_chart_partition("defending", league, season, ["whoscored_player_id", "x", "action"])
    pass_by_team, def_by_team, attack_by_team = {}, {}, {}
    if passes is not None and len(passes):
        p = passes.copy()
        p["team"] = p["whoscored_player_id"].astype("int64").map(team_of)
        p = p.dropna(subset=["team"])
        p["len_m"] = ((((p["end_x"] - p["x"]) * PITCH_X / 100) ** 2 + ((p["end_y"] - p["y"]) * PITCH_Y / 100) ** 2) ** 0.5)
        g = p.groupby("team")
        pass_by_team = {t: {"directness": 100 * float(x["progressive"].astype(float).mean()),
                            "pass_length": float(x["len_m"].mean()),
                            "final_third": 100 * float((x["x"] >= FINAL_THIRD_X).mean())} for t, x in g}
        attack_by_team = {t: _attack_channels(x) for t, x in g}
    if defs is not None and len(defs):
        d = defs[defs["action"].isin(["tackle", "interception", "recovery"])].copy()
        d["team"] = d["whoscored_player_id"].astype("int64").map(team_of)
        d = d.dropna(subset=["team"])
        def_by_team = {t: float(x["x"].mean()) * PITCH_X / 100 for t, x in d.groupby("team")}

    out = []
    for team, g in tm.groupby("team", sort=False):
        n = len(g)
        def_actions = g["tackles"].sum() + g["interceptions"].sum() + g["fouls"].sum()
        vals = {
            "possession": 100 * float(g["poss"].mean()) if g["poss"].notna().any() else None,
            "pass_accuracy": 100 * _safe_div(g["passes_acc"].sum(), g["passes"].sum()) if g["passes"].sum() else None,
            "ppda": _safe_div(g["opp_passes"].sum(), def_actions),
            "def_height": def_by_team.get(team),
            "shots": float(g["shots"].sum()) / n,
            "xg": float(g["xg"].sum()) / n,
            "xga": float(g["opp_xg"].fillna(0).sum()) / n,
            "xg_per_shot": _safe_div(g["xg"].sum(), g["shots"].sum()),
            "aerial_win": 100 * _safe_div(g["aerials_won"].sum(), g["aerials"].sum()) if g["aerials"].sum() else None,
            "takeons": float(g["dribbles"].sum()) / n,
            **pass_by_team.get(team, {}),
        }
        clean = {k: (None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), 3)) for k, v in vals.items()}
        row = {"team": team, "matches": int(n), "values": clean}
        att = attack_by_team.get(team)
        if att:
            att = dict(att)
            entries, box = att.pop("_entries"), att.pop("_box")
            row["attack"] = {**att, "entries_per_match": round(entries / n, 1), "box_per_match": round(box / n, 1)}
        out.append(row)
    out.sort(key=lambda r: r["team"])
    return out


def _attack_channels(p) -> dict:
    """Where a team gets into the final third: completed passes that start before it and end inside it,
    split by the channel they end in. Opta's y runs from the attacking team's right touchline (0) to its
    left (100), so "left" is y above two thirds."""
    done = p["completed"].astype(bool) if "completed" in p else p["x"].notna()
    entry = p[done & (p["x"] < FINAL_THIRD_X) & (p["end_x"] >= FINAL_THIRD_X)]
    n = len(entry)
    if not n:
        return {}
    left = int((entry["end_y"] > 200 / 3).sum())
    right = int((entry["end_y"] < 100 / 3).sum())
    box = int((done & p["into_box"].astype(bool)).sum()) if "into_box" in p else 0
    return {"left": round(100 * left / n, 1), "centre": round(100 * (n - left - right) / n, 1),
            "right": round(100 * right / n, 1), "_entries": n, "_box": box}


def with_ranks(rows: list[dict]) -> list[dict]:
    """Adds {key: rank} per team (1 = highest, or lowest for "low" metrics); ties share a rank."""
    for key, _l, _u, _d, order, _desc in METRICS:
        place = {}
        for r in rows:
            v = r["values"].get(key)
            if v is None:
                continue
            place.setdefault(v, 1 + sum(1 for o in rows if o["values"].get(key) is not None and
                                        (o["values"][key] > v if order == "high" else o["values"][key] < v)))
        for r in rows:
            v = r["values"].get(key)
            r.setdefault("ranks", {})[key] = place.get(v) if v is not None else None
    return rows


_CACHE: dict = {}


def team_styles(league: str, season: str) -> list[dict]:
    """Ranked team styles for one competition-season: from the extras file when it has them (built
    with the data), otherwise computed once here and kept."""
    from core.advanced import extras
    key = f"{league}|{season}"
    f = extras.teams_file()
    rows = f.get(key) if f else None
    if rows is None:
        if key not in _CACHE:
            _CACHE[key] = compute(league, season)
        rows = _CACHE[key]
    return with_ranks([{**r, "values": dict(r["values"]), **({"attack": dict(r["attack"])} if r.get("attack") else {})}
                       for r in rows])


def team_players(league: str, season: str, team: str):
    """This team's player-season rows (the advanced table), most minutes first."""
    from core.advanced import store
    df = store.get_advanced_df()
    t = df[(df["league"] == league) & (df["season"] == season) & (df["team_name"] == team)]
    return t.sort_values("total_minutes", ascending=False)


def pass_network(league: str, season: str, team: str, size: int = 11) -> dict:
    """The team's most-used players placed at the average position of their touches, joined by how
    often they pass to each other (both directions added up), from the link-up pairs."""
    import pyarrow.dataset as ds
    from core.advanced import config, store
    from core.advanced.overview import GRID_X, GRID_Y
    players = team_players(league, season, team).head(size)
    hset = store._overview_dataset("heat", config.HEATMAPS_DIR)
    heat_by = {}
    if hset is not None and len(players):
        pids = [int(x) for x in players["whoscored_player_id"]]
        tbl = hset.to_table(columns=["whoscored_player_id", "touches"],
                            filter=(ds.field("league") == league) & (ds.field("season") == season) & ds.field("whoscored_player_id").isin(pids))
        heat_by = {int(a): b for a, b in zip(tbl.column("whoscored_player_id").to_pylist(), tbl.column("touches").to_pylist())}
    nodes, ids = [], set()
    for _, r in players.iterrows():
        pid = int(r["whoscored_player_id"])
        t = heat_by.get(pid)
        if not t or not sum(t):
            continue
        tot = float(sum(t))
        x = sum(v * ((i // GRID_Y) + 0.5) for i, v in enumerate(t)) / tot * 100 / GRID_X
        y = sum(v * ((i % GRID_Y) + 0.5) for i, v in enumerate(t)) / tot * 100 / GRID_Y
        nodes.append({"id": pid, "name": r["player_name"], "position": r.get("position"), "minutes": int(r["total_minutes"]),
                      "x": round(x, 1), "y": round(y, 1), "touches": int(tot)})
        ids.add(pid)
    pair: dict = {}
    for n in nodes:
        for e in store.get_linkup_pairs(n["id"], league, season):
            rid = int(e["receiver_id"])
            if rid in ids and rid != n["id"]:
                k = tuple(sorted((n["id"], rid)))
                pair[k] = pair.get(k, 0) + int(e["count"])
    for n in nodes:
        n["passes"] = sum(c for (a, b), c in pair.items() if n["id"] in (a, b))
    edges = sorted(({"a": a, "b": b, "n": c} for (a, b), c in pair.items()), key=lambda e: -e["n"])
    return {"nodes": nodes, "edges": edges}


def team_shots(league: str, season: str, team: str) -> list[dict]:
    """Every shot by the team's players in that competition-season (location, xG, outcome)."""
    from core.advanced import config, store
    import pyarrow.dataset as ds
    pids = [int(p) for p in team_players(league, season, team)["whoscored_player_id"]]
    dset = store._overview_dataset("shots", config.SHOTS_DIR)
    if dset is None or not pids:
        return []
    cols = [c for c in ("x", "y", "xg", "outcome", "situation", "body", "big_chance", "minute", "gm_y", "gm_z")
            if c in dset.schema.names]
    flt = (ds.field("league") == league) & (ds.field("season") == season) & ds.field("whoscored_player_id").isin(pids)
    return dset.to_table(columns=cols, filter=flt).to_pylist()


def build_all(league_seasons) -> dict:
    """{"league|season": rows} for the extras file."""
    return {f"{lg}|{sn}": compute(lg, sn) for lg, sn in league_seasons}
