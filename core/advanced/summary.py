"""
Request-time shaping of the Overview data (see overview.py / the
build_overview_data.py script that produces it): season stat line, recent
form, career table and the auto "strengths / weaknesses" text.

Everything here works on a single player's rows (a few dozen match rows),
never a whole table.
"""

import re

_SUM_KEYS = ("goals", "pens_scored", "assists", "yellow", "red", "shots", "sot", "key_passes",
             "passes", "passes_acc", "touches", "tackles", "tackles_won", "interceptions",
             "clearances", "aerials", "aerials_won", "dribbles", "dribbles_won", "fouls", "saves")


def _f(v, nd=2):
    return None if v is None else round(float(v), nd)


def season_line(rows: list[dict]) -> dict:
    """Totals + per-90s + average rating for one player-season's match rows."""
    if not rows:
        return {}
    mins = sum(r["minutes"] for r in rows)
    out = {
        "apps": len(rows),
        "starts": sum(1 for r in rows if r["started"]),
        "minutes": int(round(mins)),
        "motm": sum(1 for r in rows if r["motm"]),
        "xg": _f(sum(r["xg"] for r in rows), 1),
        "npxg": _f(sum(r["npxg"] for r in rows), 1),
        "xa": _f(sum(r["xa"] for r in rows), 1),
    }
    for k in _SUM_KEYS:
        out[k] = int(sum(r.get(k) or 0 for r in rows))
    out["npg"] = out["goals"] - out["pens_scored"]
    rated = [(r["rating"], r["minutes"]) for r in rows if r.get("rating") is not None]
    out["avg_rating"] = _f(sum(v for v, _ in rated) / len(rated), 2) if rated else None
    out["pass_pct"] = round(100 * out["passes_acc"] / out["passes"], 1) if out["passes"] else None
    out["tackle_pct"] = round(100 * out["tackles_won"] / out["tackles"], 1) if out["tackles"] else None
    out["aerial_pct"] = round(100 * out["aerials_won"] / out["aerials"], 1) if out["aerials"] else None
    out["dribble_pct"] = round(100 * out["dribbles_won"] / out["dribbles"], 1) if out["dribbles"] else None
    out["clean_sheets"] = sum(1 for r in rows if r.get("ga") == 0 and r["minutes"] >= 60)
    out["goals_conceded"] = int(sum(r["ga"] for r in rows if r.get("ga") is not None))
    if mins >= 90:
        n90 = mins / 90.0
        out["per90"] = {
            "goals": _f(out["goals"] / n90), "assists": _f(out["assists"] / n90),
            "xg": _f(out["xg"] / n90), "npxg": _f(out["npxg"] / n90), "xa": _f(out["xa"] / n90),
            "shots": _f(out["shots"] / n90), "key_passes": _f(out["key_passes"] / n90),
            "tackles": _f(out["tackles"] / n90), "interceptions": _f(out["interceptions"] / n90),
        }
    return out


def _result(r: dict) -> str | None:
    if r.get("gf") is None or r.get("ga") is None:
        return None
    return "W" if r["gf"] > r["ga"] else ("L" if r["gf"] < r["ga"] else "D")


def form(rows: list[dict], n: int = 38) -> list[dict]:
    """Most recent `n` matches, oldest -> newest (chart order)."""
    ordered = sorted(rows, key=lambda r: (r.get("date") or "", r.get("match_key") or ""))[-n:]
    return [{
        "date": r.get("date"), "opp": r.get("opp"), "home": bool(r.get("home")),
        "gf": r.get("gf"), "ga": r.get("ga"), "result": _result(r),
        "rating": r.get("rating"), "minutes": int(round(r["minutes"])), "started": bool(r["started"]),
        "goals": r["goals"], "assists": r["assists"], "xg": _f(r["xg"]), "motm": bool(r["motm"]),
        "yellow": r["yellow"], "red": r["red"],
    } for r in ordered]


def career(rows: list[dict]) -> list[dict]:
    """One line per (league, season) the player appears in, newest first."""
    groups: dict = {}
    for r in rows:
        groups.setdefault((r["league"], r["season"]), []).append(r)
    out = []
    for (league, season), g in groups.items():
        line = season_line(g)
        last = sorted(g, key=lambda r: r.get("date") or "")[-1]
        out.append({
            "league": league, "season": season, "team": last.get("team"),
            "apps": line["apps"], "minutes": line["minutes"], "goals": line["goals"],
            "assists": line["assists"], "xg": line["xg"], "xa": line["xa"],
            "avg_rating": line["avg_rating"], "yellow": line["yellow"], "red": line["red"],
        })
    from core.advanced.config import season_sort_key
    out.sort(key=lambda c: season_sort_key(c["season"]), reverse=True)
    return out


LIMITED_FLOOR_MIN = 450      # matches config.ADV_MIN_MINUTES (the percentile cohort floor)
LIMITED_TEAM_SHARE = 1 / 3   # ...but only "limited" if also under this share of the team's minutes


def sample_info(minutes: float, team_matches: int, floor: int = LIMITED_FLOOR_MIN, progress: float = 1.0) -> dict:
    """Is this player-season a thin sample? A flat minutes floor misfires in
    short competitions (a Europa League regular can total ~420 min because
    the whole competition is ~a dozen games), so below the floor it only
    counts as limited if the player also played under a third of the minutes
    their team did. With no team data we fall back to the plain floor."""
    available = int(team_matches) * 90 if team_matches else 0
    share = (minutes / available) if available else None
    limited = minutes < floor and (share is None or share < LIMITED_TEAM_SHARE)
    note = ""
    if limited:
        of_team = f" of about {available:,} the team played ({share:.0%})" if share is not None else ""
        note = (f"{int(minutes)} minutes played{of_team}. Percentiles rank players with {floor}+ minutes, "
                f"so read these numbers with caution.")
    early = progress is not None and progress < 1.0
    early_note = (f"Only {progress:.0%} of this season has been played. Ratio stats (win rates, accuracy, success) "
                  f"rest on just a few events, so percentiles can swing a lot from week to week.") if early else ""
    return {"limited": limited, "minutes": int(minutes), "team_minutes": available or None, "note": note,
            "early_season": early, "early_note": early_note}


# Metrics where being *low* in the cohort is a real weakness (rates of doing
# a thing well). A low count of e.g. headed shots just means "a different
# kind of player", so it is never listed as a weakness.
_QUALITY = re.compile(r"accuracy|success|conversion|completion", re.I)


def insights(categories: list[dict], n_strengths: int = 4, n_weak: int = 3) -> dict:
    """Strengths / areas-to-improve from the percentile stats the
    Advanced Metrics tabs already show (position-group cohort percentiles)."""
    scored = []
    for cat in categories:
        for row in cat.get("rows", []):
            for s in row.get("stats", []):
                if s.get("no_data") or s.get("percentile") is None:
                    continue
                scored.append({"label": s["label"], "category": cat["label"], "percentile": s["percentile"],
                               "value": s.get("value"), "unit": s.get("unit", "")})
    strengths = sorted((s for s in scored if s["percentile"] >= 85), key=lambda s: -s["percentile"])[:n_strengths]
    weak = sorted((s for s in scored if s["percentile"] <= 20 and _QUALITY.search(s["label"])),
                  key=lambda s: s["percentile"])[:n_weak]
    return {"strengths": strengths, "weaknesses": weak}
