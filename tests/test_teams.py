"""Team style measures (core/advanced/teams.py) on a small hand-made competition."""
import pandas as pd

from core.advanced import teams


def _match_rows():
    # one match, A vs B: A has 300 passes to B's 100, so 75% possession
    base = {"match_key": "m1", "date": "2025-08-01", "home": True, "gf": 1, "ga": 0}
    rows = []
    for team, opp, passes, acc, tackles, inter, fouls, shots, xg, aer, aerw, drib in [
            ("A", "B", 150, 135, 3, 2, 1, 6, 0.9, 5, 3, 4), ("A", "B", 150, 135, 2, 1, 1, 4, 0.6, 5, 2, 2),
            ("B", "A", 60, 45, 10, 6, 4, 3, 0.2, 6, 4, 1), ("B", "A", 40, 30, 8, 4, 3, 1, 0.1, 4, 1, 0)]:
        rows.append({**base, "team": team, "opp": opp, "passes": passes, "passes_acc": acc, "tackles": tackles,
                     "interceptions": inter, "fouls": fouls, "shots": shots, "xg": xg, "aerials": aer,
                     "aerials_won": aerw, "dribbles": drib})
    return pd.DataFrame(rows)


def _compute():
    players = pd.DataFrame({"whoscored_player_id": [1, 2], "team_name": ["A", "B"]})
    passes = pd.DataFrame({"whoscored_player_id": [1, 1, 2, 2], "x": [50, 80, 20, 30], "y": [50, 50, 50, 50],
                           "end_x": [60, 90, 30, 30], "end_y": [50, 50, 50, 60], "progressive": [True, False, False, False]})
    defs = pd.DataFrame({"whoscored_player_id": [1, 1, 2, 2], "x": [60, 40, 20, 20],
                         "action": ["tackle", "recovery", "interception", "clearance"]})
    return {r["team"]: r for r in teams.with_ranks(teams.compute("L", "S", matches=_match_rows(), players=players,
                                                                    passes=passes, defs=defs))}


def test_match_based_measures():
    t = _compute()
    a, b = t["A"]["values"], t["B"]["values"]
    assert a["possession"] == 75.0 and b["possession"] == 25.0
    assert a["pass_accuracy"] == 90.0 and b["pass_accuracy"] == 75.0
    assert a["ppda"] == round(100 / 10, 3)                  # B's 100 passes over A's 3+2+1+2+1+1 = 10 actions
    assert b["ppda"] == round(300 / 35, 3)
    assert a["xg"] == 1.5 and a["xga"] == 0.3 and a["shots"] == 10.0


def test_event_based_measures():
    t = _compute()
    a, b = t["A"]["values"], t["B"]["values"]
    assert a["directness"] == 50.0 and b["directness"] == 0.0
    assert a["final_third"] == 50.0                          # one of A's two passes starts at x >= 66.7
    assert a["def_height"] == round(50 * 1.05, 3)            # tackle at 60 and recovery at 40 -> 50 -> 52.5 m
    assert b["def_height"] == round(20 * 1.05, 3)            # the clearance is not a ball-winning action
    assert a["pass_length"] == round(10 * 1.05, 3)


def test_ranks_follow_each_measures_direction():
    t = _compute()
    assert t["A"]["ranks"]["possession"] == 1 and t["B"]["ranks"]["possession"] == 2
    assert t["B"]["ranks"]["ppda"] == 1 and t["A"]["ranks"]["ppda"] == 2      # B allows 8.6 passes per action, A 10: B presses more
    assert t["A"]["ranks"]["xga"] == 1                                        # less xG against ranks first


def test_metric_list_is_consistent():
    keys = [m["key"] for m in teams.META]
    assert len(keys) == len(set(keys)) and all(m["order"] in ("high", "low") for m in teams.META)
