"""Unit tests for the Overview feature: xG geometry/model, per-match
extraction (using a tiny synthetic match, no real data needed) and the
request-time summary shaping."""
import numpy as np
import pytest

from core.advanced import xg
from core.advanced.overview import extract_match
from core.advanced.summary import season_line, form, insights


# ── xG ───────────────────────────────────────────────────────────────────────

def test_shot_geometry_penalty_spot_is_about_11m():
    dist, _ = xg.shot_geometry(100 - 11 / 105 * 100, 50)
    assert dist == pytest.approx(11, abs=0.05)


def test_angle_wider_close_in_than_far_out():
    _, close = xg.shot_geometry(95, 50)
    _, far = xg.shot_geometry(70, 50)
    assert close > far


def test_angle_narrower_from_tight_wide_position():
    _, central = xg.shot_geometry(94, 50)
    _, wide = xg.shot_geometry(94, 10)
    assert central > wide


def test_fit_predict_ranks_close_big_chance_above_long_shot():
    rng = np.random.default_rng(0)
    rows, labels = [], []
    for _ in range(4000):
        x, y = rng.uniform(70, 99), rng.uniform(20, 80)
        big = rng.random() < 0.1
        feats = xg.feature_vector(x, y, {"big_chance": big})
        dist = feats[0]
        p = 1 / (1 + np.exp(-(1.2 - 0.18 * dist + 1.5 * big)))
        rows.append(feats)
        labels.append(float(rng.random() < p))
    model = xg.fit(np.array(rows), np.array(labels), penalty_rate=0.78)
    good = xg.predict(model, np.array([xg.feature_vector(96, 50, {"big_chance": True})]))[0]
    poor = xg.predict(model, np.array([xg.feature_vector(70, 25, {})]))[0]
    assert good > 0.4 > poor
    assert 0 < poor < good < 1


# ── extract_match on a synthetic match ──────────────────────────────────────

def _ev(seq, team, pid, typ, x, y, minute, quals=(), **kw):
    return {"seq_id": seq, "team_id": team, "player_id": pid, "type": typ, "x": x, "y": y,
            "minute": minute, "period": "FirstHalf", "qualifiers": [{"type": {"displayName": q}, "value": v} for q, v in quals],
            "is_touch": kw.get("is_touch", True), "card_type": kw.get("card_type"), "outcome_type": "Successful"}


def _match():
    # Team 1 (home) player 10 passes to player 11 who scores. The *away* team
    # also has an event numbered seq 5 -- eventId is per-team, so the assist
    # lookup must not be fooled by it.
    events = [
        _ev(5, 2, 20, "Pass", 40, 40, 30),
        _ev(5, 1, 10, "Pass", 80, 60, 33, [("KeyPass", None)]),
        _ev(6, 1, 11, "Goal", 92, 50, 33, [("Assisted", None), ("RelatedEventId", "5"), ("RightFoot", None), ("BigChance", None)]),
        _ev(7, 1, 11, "MissedShots", 85, 30, 60, [("Head", None)]),
        _ev(8, 1, 12, "Card", 50, 50, 70, card_type="Yellow", is_touch=False),
    ]
    def pl(pid, first=True, name="P"):
        return {"playerId": pid, "isFirstEleven": first, "position": "FW", "isManOfTheMatch": pid == 11,
                "stats": {"passesTotal": {"1": 10}, "passesAccurate": {"1": 8}, "ratings": {"1": 6.5, "90": 8.1}}}
    mj = {"score": "1 : 0", "startTime": "2025-01-02T15:00:00",
          "home": {"name": "A", "players": [pl(10), pl(11), pl(12)]}, "away": {"name": "B", "players": [pl(20)]}}
    return mj, events, {10: 90.0, 11: 90.0, 12: 90.0, 20: 90.0}


def test_extract_match_goal_assist_and_cards():
    mj, events, mins = _match()
    rows, shots, heat = extract_match("m1", mj, events, mins)
    by = {r["whoscored_player_id"]: r for r in rows}
    assert by[11]["goals"] == 1 and by[11]["shots"] == 2 and by[11]["sot"] == 1
    assert by[10]["assists"] == 1            # credited to the home passer, not away player 20
    assert by[20]["assists"] == 0
    assert by[12]["yellow"] == 1
    assert by[11]["motm"] is True and by[11]["rating"] == 8.1   # final rating, not the first
    assert by[11]["gf"] == 1 and by[11]["ga"] == 0 and by[20]["gf"] == 0 and by[20]["ga"] == 1
    assert by[10]["passes"] == 10 and by[10]["passes_acc"] == 8
    assert len(shots) == 2 and shots[0]["assist_pid"] == 10 and shots[0]["big_chance"] is True
    assert shots[1]["body"] == "head"


def test_extract_match_heat_grid_counts_touches():
    mj, events, mins = _match()
    _, _, heat = extract_match("m1", mj, events, mins)
    touches, _defs = heat[11]
    assert touches.sum() == 2                # goal + missed shot events with is_touch


def test_extract_match_skips_players_who_did_not_play():
    mj, events, mins = _match()
    mins[12] = 0.0
    rows, _, _ = extract_match("m1", mj, events, mins)
    assert 12 not in {r["whoscored_player_id"] for r in rows}


# ── summary ──────────────────────────────────────────────────────────────────

def _row(**kw):
    base = {"minutes": 90.0, "started": True, "motm": False, "rating": 7.0, "goals": 0, "pens_scored": 0, "assists": 0,
            "yellow": 0, "red": 0, "shots": 0, "sot": 0, "key_passes": 0, "passes": 40, "passes_acc": 32, "touches": 60,
            "tackles": 2, "tackles_won": 1, "interceptions": 1, "clearances": 0, "aerials": 2, "aerials_won": 1,
            "dribbles": 1, "dribbles_won": 1, "fouls": 1, "saves": 0, "xg": 0.0, "npxg": 0.0, "xa": 0.0,
            "gf": 1, "ga": 0, "date": "2025-01-01", "match_key": "a", "home": True, "opp": "X"}
    base.update(kw)
    return base


def test_season_line_totals_and_derived():
    rows = [_row(goals=2, pens_scored=1, xg=0.9, npxg=0.1, rating=8.0, date="2025-01-01", match_key="a"),
            _row(goals=0, ga=2, gf=0, rating=6.0, minutes=45.0, started=False, date="2025-01-08", match_key="b")]
    line = season_line(rows)
    assert line["apps"] == 2 and line["starts"] == 1 and line["minutes"] == 135
    assert line["goals"] == 2 and line["npg"] == 1
    assert line["avg_rating"] == 7.0
    assert line["pass_pct"] == 80.0
    assert line["clean_sheets"] == 1          # 2nd game was 45' only and conceded 2
    assert line["per90"]["goals"] == pytest.approx(1.33, abs=0.01)


def test_form_is_chronological_and_has_result():
    rows = [_row(date="2025-02-01", match_key="b", gf=0, ga=1), _row(date="2025-01-01", match_key="a")]
    f = form(rows)
    assert [m["date"] for m in f] == ["2025-01-01", "2025-02-01"]
    assert [m["result"] for m in f] == ["W", "L"]


def test_insights_only_flags_quality_metrics_as_weaknesses():
    cats = [{"label": "Cat", "rows": [{"stats": [
        {"label": "Progressive passes", "percentile": 95, "value": 5, "unit": ""},
        {"label": "Headed shots", "percentile": 3, "value": 0, "unit": ""},          # style, not a weakness
        {"label": "Cross accuracy", "percentile": 8, "value": 10, "unit": "%"},      # quality -> weakness
        {"label": "Tackle success", "percentile": 50, "value": 60, "unit": "%"},
    ]}]}]
    out = insights(cats)
    assert [s["label"] for s in out["strengths"]] == ["Progressive passes"]
    assert [s["label"] for s in out["weaknesses"]] == ["Cross accuracy"]


# ── limited-sample rule ──────────────────────────────────────────────────────
from core.advanced.summary import sample_info


def test_europa_league_regular_is_not_limited():
    # 420 min of a ~12-match competition (1080 available) = 39% of the team's minutes
    assert sample_info(420, 12)["limited"] is False


def test_league_fringe_player_is_limited():
    s = sample_info(300, 38)           # 300 of 3420 = 9%
    assert s["limited"] is True and "300 minutes" in s["note"] and "450+" in s["note"]


def test_above_floor_never_limited():
    assert sample_info(900, 38)["limited"] is False


def test_unknown_team_matches_falls_back_to_plain_floor():
    assert sample_info(400, 0)["limited"] is True
    assert sample_info(500, 0)["limited"] is False
