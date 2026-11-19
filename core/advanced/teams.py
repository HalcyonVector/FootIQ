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

ATT, CRE, POS, DEF, DUEL, GK, ALL = ("Attacking", "Chance creation", "Possession and passing", "Defending and pressing",
                                     "Duels and discipline", "Goalkeeping", "Overall")

# key, label, unit, decimals, rank order ("high" = biggest value ranks 1st), group, what it means
METRICS = [
    # attacking
    ("goals", "Goals per match", "", 2, "high", ATT, "Goals scored per match."),
    ("xg", "xG per match", "", 2, "high", ATT, "Expected goals per match, from our own model."),
    ("npxg", "Non-penalty xG per match", "", 2, "high", ATT, "Expected goals per match without penalties."),
    ("shots", "Shots per match", "", 1, "high", ATT, "Shots per match."),
    ("sot", "Shots on target per match", "", 1, "high", ATT, "Shots on target per match."),
    ("shot_accuracy", "Shots on target", "%", 1, "high", ATT, "Share of its shots that hit the target."),
    ("conversion", "Shot conversion", "%", 1, "high", ATT, "Share of its shots that are goals."),
    ("xg_per_shot", "xG per shot", "", 2, "high", ATT, "Average quality of its chances."),
    ("big_chances", "Big chances per match", "", 2, "high", ATT, "Shots from clear-cut chances per match."),
    ("shot_distance", "Average shot distance", "m", 1, "low", ATT, "How far from goal it shoots, on average. Lower means it works the ball closer."),
    ("box_shots", "Shots from inside the box", "%", 1, "high", ATT, "Share of its shots taken inside the penalty area."),
    ("setpiece_xg", "xG from set pieces", "%", 1, "high", ATT, "Share of its xG that comes from set pieces (corners, free kicks, throw-ins, penalties)."),
    ("headed_share", "Headed shots", "%", 1, "high", ATT, "Share of its shots that are headers."),
    # chance creation
    ("key_passes", "Key passes per match", "", 1, "high", CRE, "Passes that lead to a shot, per match."),
    ("xa", "xA per match", "", 2, "high", CRE, "Expected assists per match: the xG of the shots its passes set up."),
    ("ft_entries", "Passes into the final third per match", "", 1, "high", CRE, "Completed passes that start before the attacking third and end inside it."),
    ("box_passes", "Passes into the box per match", "", 1, "high", CRE, "Completed passes into the penalty area per match."),
    ("takeons", "Take-ons per match", "", 1, "high", CRE, "Attempted dribbles past an opponent per match."),
    ("takeon_success", "Take-on success", "%", 1, "high", CRE, "Share of its take-ons that beat the opponent."),
    # possession and passing
    ("possession", "Possession", "%", 1, "high", POS, "Share of the passes in its matches. Passes stand in for time on the ball."),
    ("passes", "Passes per match", "", 0, "high", POS, "Passes attempted per match."),
    ("pass_accuracy", "Pass accuracy", "%", 1, "high", POS, "Completed passes as a share of all passes."),
    ("touches", "Touches per match", "", 0, "high", POS, "Touches of the ball per match."),
    ("prog_passes", "Progressive passes per match", "", 1, "high", POS, "Passes that move the ball a good distance towards goal, per match."),
    ("directness", "Directness", "%", 1, "high", POS, "Share of its passes that are progressive."),
    ("pass_length", "Average pass length", "m", 1, "high", POS, "Average length of its passes."),
    ("long_balls", "Long balls", "%", 1, "high", POS, "Share of its passes longer than 32 m."),
    ("final_third", "Passes in the final third", "%", 1, "high", POS, "Share of its passes played in the attacking third."),
    ("release", "Time on the ball before a pass", "s", 2, "low", POS, "Average seconds between receiving the ball and passing it. Lower means quicker circulation."),
    # defending and pressing
    ("ppda", "Pressing (passes allowed per defensive action)", "", 1, "low", DEF,
     "Opponent passes for each of the team's tackles, interceptions and fouls, over the whole pitch. Lower means more pressing."),
    ("def_height", "Ball-winning height", "m", 1, "high", DEF,
     "Average distance from its own goal of the tackles, interceptions and recoveries its players make. Higher means it wins the ball further up."),
    ("high_regains", "Ball wins in the final third per match", "", 1, "high", DEF, "Tackles, interceptions and recoveries in the attacking third, per match."),
    ("recoveries", "Recoveries per match", "", 1, "high", DEF, "Loose balls won back per match."),
    ("tackles", "Tackles per match", "", 1, "high", DEF, "Tackles attempted per match."),
    ("tackle_success", "Tackle success", "%", 1, "high", DEF, "Share of its tackles won."),
    ("interceptions", "Interceptions per match", "", 1, "high", DEF, "Passes cut out per match."),
    ("clearances", "Clearances per match", "", 1, "high", DEF, "Clearances per match (high for teams that defend their box a lot)."),
    ("blocks", "Blocks per match", "", 1, "high", DEF, "Shots and passes blocked per match."),
    ("opp_shots", "Shots conceded per match", "", 1, "low", DEF, "Opponent shots per match. Lower is better."),
    ("xga", "xG against per match", "", 2, "low", DEF, "Expected goals conceded per match. Lower is better."),
    ("ga", "Goals conceded per match", "", 2, "low", DEF, "Goals conceded per match. Lower is better."),
    # duels and discipline
    ("aerials", "Aerial duels per match", "", 1, "high", DUEL, "Aerial duels contested per match."),
    ("aerial_win", "Aerial duels won", "%", 1, "high", DUEL, "Share of its aerial duels won."),
    ("fouls", "Fouls per match", "", 1, "low", DUEL, "Fouls committed per match. Lower ranks first."),
    ("yellows", "Yellow cards per match", "", 2, "low", DUEL, "Yellow cards per match. Lower ranks first."),
    # goalkeeping
    ("save_pct", "Save percentage", "%", 1, "high", GK, "Share of the opponents' shots on target its goalkeepers saved."),
    ("saves", "Saves per match", "", 1, "high", GK, "Saves per match (high for teams that face a lot)."),
    # overall
    ("ppm", "Points per match", "", 2, "high", ALL, "League points per match (3 for a win, 1 for a draw)."),
    ("gd", "Goal difference per match", "", 2, "high", ALL, "Goals scored minus conceded, per match."),
    ("xgd", "xG difference per match", "", 2, "high", ALL, "xG minus xG against, per match: how much better than its opponents it plays."),
    ("rating", "Average player rating", "", 2, "high", ALL, "WhoScored match ratings of its players, weighted by minutes."),
]
META = [{"key": k, "label": l, "unit": u, "decimals": d, "order": o, "group": g, "desc": desc} for k, l, u, d, o, g, desc in METRICS]
LONG_BALL_M = 32.0


def _safe_div(a, b):
    return float(a) / float(b) if b else None


def _pct(a, b):
    v = _safe_div(a, b)
    return None if v is None else 100 * v


def compute(league: str, season: str, matches=None, players=None, passes=None, defs=None, shots=None) -> list[dict]:
    """[{team, matches, values: {key: value}, attack}] for one competition-season. The tables can be
    passed in (tests do); otherwise they are read from the stored dataset."""
    import pandas as pd
    from core.advanced import store

    if matches is None:
        matches = store.get_season_matches(league, season)
    if matches is None or matches.empty:
        return []
    num = ["passes", "passes_acc", "tackles", "tackles_won", "interceptions", "clearances", "fouls", "shots", "sot", "xg",
           "npxg", "xa", "key_passes", "touches", "aerials", "aerials_won", "dribbles", "dribbles_won", "yellow", "saves"]
    m = matches.copy()
    for c in num:
        m[c] = pd.to_numeric(m[c], errors="coerce").fillna(0) if c in m else 0.0
    m["minutes"] = pd.to_numeric(m["minutes"], errors="coerce").fillna(0) if "minutes" in m else 0.0
    m["rating"] = pd.to_numeric(m["rating"], errors="coerce") if "rating" in m else float("nan")
    m["rmin"] = (m["rating"] * m["minutes"]).fillna(0)
    m["rated_min"] = m["minutes"].where(m["rating"].notna(), 0)
    tm = m.groupby(["match_key", "team"], sort=False).agg(
        opp=("opp", "first"), gf=("gf", "first"), ga=("ga", "first"), rmin=("rmin", "sum"), rated_min=("rated_min", "sum"),
        **{c: (c, "sum") for c in num}).reset_index()
    opp = tm[["match_key", "team", "passes", "xg", "shots", "sot"]].rename(
        columns={"team": "opp", "passes": "opp_passes", "xg": "opp_xg", "shots": "opp_shots", "sot": "opp_sot"})
    tm = tm.merge(opp, on=["match_key", "opp"], how="left")
    tm["poss"] = tm["passes"] / (tm["passes"] + tm["opp_passes"])
    tm["gf"] = pd.to_numeric(tm["gf"], errors="coerce")
    tm["ga"] = pd.to_numeric(tm["ga"], errors="coerce")
    tm["pts"] = (tm["gf"] > tm["ga"]) * 3 + (tm["gf"] == tm["ga"]) * 1

    # event coordinates, joined to the player's team for this season
    if players is None:
        df = store.get_advanced_df()
        players = df[(df["league"] == league) & (df["season"] == season)][["whoscored_player_id", "team_name"]]
    team_of = dict(zip(players["whoscored_player_id"].astype("int64"), players["team_name"]))
    if passes is None:
        passes = store.get_chart_partition("passing", league, season,
                                           ["whoscored_player_id", "x", "y", "end_x", "end_y", "progressive", "completed",
                                            "into_box", "release_s"])
    if defs is None:
        defs = store.get_chart_partition("defending", league, season, ["whoscored_player_id", "x", "action"])
    if shots is None:
        shots = _season_shots(league, season)
    pass_by_team, def_by_team, attack_by_team, shot_by_team = {}, {}, {}, {}
    if passes is not None and len(passes):
        p = passes.copy()
        p["team"] = p["whoscored_player_id"].astype("int64").map(team_of)
        p = p.dropna(subset=["team"])
        p["len_m"] = ((((p["end_x"] - p["x"]) * PITCH_X / 100) ** 2 + ((p["end_y"] - p["y"]) * PITCH_Y / 100) ** 2) ** 0.5)
        for t, x in p.groupby("team"):
            prog = x["progressive"].astype(float)
            pass_by_team[t] = {"directness": 100 * float(prog.mean()), "pass_length": float(x["len_m"].mean()),
                               "final_third": 100 * float((x["x"] >= FINAL_THIRD_X).mean()),
                               "long_balls": 100 * float((x["len_m"] >= LONG_BALL_M).mean()),
                               "release": float(x["release_s"].mean()) if "release_s" in x and x["release_s"].notna().any() else None,
                               "_prog": float(prog.sum())}
            attack_by_team[t] = _attack_channels(x)
    if defs is not None and len(defs):
        d = defs.copy()
        d["team"] = d["whoscored_player_id"].astype("int64").map(team_of)
        d = d.dropna(subset=["team"])
        wins = d[d["action"].isin(["tackle", "interception", "recovery"])]
        for t, x in wins.groupby("team"):
            def_by_team.setdefault(t, {})["def_height"] = float(x["x"].mean()) * PITCH_X / 100
            def_by_team[t]["_high"] = int((x["x"] >= FINAL_THIRD_X).sum())
        for t, x in d.groupby("team"):
            def_by_team.setdefault(t, {})["_recoveries"] = int((x["action"] == "recovery").sum())
            def_by_team[t]["_blocks"] = int((x["action"] == "block").sum())
    if shots is not None and len(shots):
        s = shots.copy()
        s["team"] = s["whoscored_player_id"].astype("int64").map(team_of)
        s = s.dropna(subset=["team"])
        s["dist"] = ((((100 - s["x"]) * PITCH_X / 100) ** 2 + ((50 - s["y"]) * PITCH_Y / 100) ** 2) ** 0.5)
        for t, x in s.groupby("team"):
            xg = float(x["xg"].sum())
            sp = x["situation"].astype(str).str.lower().ne("open_play") if "situation" in x else None
            shot_by_team[t] = {
                "shot_distance": float(x["dist"].mean()),
                "box_shots": 100 * float(((x["x"] >= 83) & (x["y"] >= 21.1) & (x["y"] <= 78.9)).mean()),
                "setpiece_xg": 100 * float(x.loc[sp, "xg"].sum()) / xg if (sp is not None and xg) else None,
                "headed_share": 100 * float(x["body"].astype(str).str.lower().eq("head").mean()) if "body" in x else None,
                "_big": int(x["big_chance"].fillna(False).astype(bool).sum()) if "big_chance" in x else None,
            }

    out = []
    for team, g in tm.groupby("team", sort=False):
        n = len(g)
        per = lambda v: None if v is None else float(v) / n
        def_actions = g["tackles"].sum() + g["interceptions"].sum() + g["fouls"].sum()
        pb, db, sb = pass_by_team.get(team, {}), def_by_team.get(team, {}), shot_by_team.get(team, {})
        att = attack_by_team.get(team) or {}
        vals = {
            "goals": per(g["gf"].sum()), "xg": per(g["xg"].sum()), "npxg": per(g["npxg"].sum()),
            "shots": per(g["shots"].sum()), "sot": per(g["sot"].sum()),
            "shot_accuracy": _pct(g["sot"].sum(), g["shots"].sum()), "conversion": _pct(g["gf"].sum(), g["shots"].sum()),
            "xg_per_shot": _safe_div(g["xg"].sum(), g["shots"].sum()), "big_chances": per(sb.get("_big")),
            "shot_distance": sb.get("shot_distance"), "box_shots": sb.get("box_shots"),
            "setpiece_xg": sb.get("setpiece_xg"), "headed_share": sb.get("headed_share"),
            "key_passes": per(g["key_passes"].sum()), "xa": per(g["xa"].sum()),
            "ft_entries": per(att.get("_entries")), "box_passes": per(att.get("_box")),
            "takeons": per(g["dribbles"].sum()), "takeon_success": _pct(g["dribbles_won"].sum(), g["dribbles"].sum()),
            "possession": 100 * float(g["poss"].mean()) if g["poss"].notna().any() else None,
            "passes": per(g["passes"].sum()), "pass_accuracy": _pct(g["passes_acc"].sum(), g["passes"].sum()),
            "touches": per(g["touches"].sum()), "prog_passes": per(pb.get("_prog")),
            "directness": pb.get("directness"), "pass_length": pb.get("pass_length"), "long_balls": pb.get("long_balls"),
            "final_third": pb.get("final_third"), "release": pb.get("release"),
            "ppda": _safe_div(g["opp_passes"].sum(), def_actions), "def_height": db.get("def_height"),
            "high_regains": per(db.get("_high")), "recoveries": per(db.get("_recoveries")),
            "tackles": per(g["tackles"].sum()), "tackle_success": _pct(g["tackles_won"].sum(), g["tackles"].sum()),
            "interceptions": per(g["interceptions"].sum()), "clearances": per(g["clearances"].sum()),
            "blocks": per(db.get("_blocks")), "opp_shots": per(g["opp_shots"].fillna(0).sum()),
            "xga": per(g["opp_xg"].fillna(0).sum()), "ga": per(g["ga"].sum()),
            "aerials": per(g["aerials"].sum()), "aerial_win": _pct(g["aerials_won"].sum(), g["aerials"].sum()),
            "fouls": per(g["fouls"].sum()), "yellows": per(g["yellow"].sum()),
            "save_pct": _pct(g["saves"].sum(), g["opp_sot"].fillna(0).sum()), "saves": per(g["saves"].sum()),
            "ppm": per(g["pts"].sum()), "gd": per(g["gf"].sum() - g["ga"].sum()),
            "xgd": per(g["xg"].sum() - g["opp_xg"].fillna(0).sum()),
            "rating": _safe_div(g["rmin"].sum(), g["rated_min"].sum()),
        }
        clean = {k: (None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), 3)) for k, v in vals.items()}
        row = {"team": team, "matches": int(n), "values": clean}
        if att:
            att = dict(att)
            entries, box = att.pop("_entries"), att.pop("_box")
            row["attack"] = {**att, "entries_per_match": round(entries / n, 1), "box_per_match": round(box / n, 1)}
        out.append(row)
    out.sort(key=lambda r: r["team"])
    return out


def _season_shots(league: str, season: str):
    """Every shot of one competition-season (shooter, location, xG, situation, body part, big chance)."""
    import pandas as pd
    import pyarrow.dataset as ds
    from core.advanced import config, store
    dset = store._overview_dataset("shots", config.SHOTS_DIR)
    if dset is None:
        return pd.DataFrame()
    cols = [c for c in ("whoscored_player_id", "x", "y", "xg", "situation", "body", "big_chance") if c in dset.schema.names]
    return dset.to_table(columns=cols, filter=(ds.field("league") == league) & (ds.field("season") == season)).to_pandas()


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
    for meta in META:
        key, order = meta["key"], meta["order"]
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
