"""League table / team page maths, on a tiny synthetic season."""
import pandas as pd

from core.advanced import tables


def _rows():
    # 3 matches among A, B, C. Two player rows per team per match (to check the
    # collapse to one row per team-match and that xG sums per team).
    spec = [
        # match, date, home, away, hg, ag, home_xg_total, away_xg_total
        ("m1", "2026-08-01", "A", "B", 2, 0, 1.6, 0.4),
        ("m2", "2026-08-08", "B", "C", 1, 1, 0.9, 1.1),
        ("m3", "2026-08-15", "C", "A", 0, 3, 0.2, 2.4),
    ]
    out = []
    for key, date, home, away, hg, ag, hx, ax in spec:
        for team, opp, is_home, gf, ga, xg in ((home, away, True, hg, ag, hx), (away, home, False, ag, hg, ax)):
            for k in range(2):
                out.append({"match_key": key, "date": date, "team": team, "opp": opp, "home": is_home,
                            "gf": gf, "ga": ga, "xg": xg / 2, "whoscored_player_id": hash((team, k)) % 10_000,
                            "started": True, "minutes": 90.0, "pos": "FW" if k else "MC", "rating": 6.5 + k,
                            "goals": 1 if (k and gf) else 0, "assists": 0, "xa": 0.1, "yellow": 0, "red": 0})
    return pd.DataFrame(out)


def test_table_points_and_order():
    t = tables.league_table(_rows())
    assert [r["team"] for r in t] == ["A", "B", "C"]          # A 6 pts; B and C 1 pt each, B has the better GD
    a = t[0]
    assert (a["played"], a["won"], a["drawn"], a["lost"]) == (2, 2, 0, 0)
    assert (a["gf"], a["ga"], a["gd"], a["points"], a["pos"]) == (5, 0, 5, 6, 1)
    assert a["form"] == ["W", "W"]


def test_tiebreak_is_goal_difference():
    t = {r["team"]: r for r in tables.league_table(_rows())}
    assert t["B"]["points"] == t["C"]["points"] == 1
    assert t["B"]["gd"] == -2 and t["C"]["gd"] == -3           # B: 0-2, 1-1   C: 1-1, 0-3
    assert t["B"]["pos"] < t["C"]["pos"]                       # equal points -> goal difference decides


def test_xg_for_and_against_come_from_the_two_sides():
    a = next(r for r in tables.league_table(_rows()) if r["team"] == "A")
    assert a["xgf"] == 4.0 and a["xga"] == 0.6                # 1.6+2.4 for; 0.4+0.2 against


def test_team_page_squad_and_results():
    names = {}
    page = tables.team_page(_rows(), "A", names)
    assert page["pos"] == 1 and page["teams"] == 3
    assert [r["opp"] for r in page["results"]] == ["B", "C"] and page["results"][1]["home"] is False
    assert len(page["squad"]) == 2 and all(p["apps"] == 2 for p in page["squad"])
    assert page["squad"][0]["name"].startswith("Player ")     # fallback when the id has no known name
    assert tables.team_page(_rows(), "Nope", names) is None


def test_empty_input():
    assert tables.league_table(pd.DataFrame()) == []
