"""
Chart specs for every Advanced Metrics tab, Combination Play and Compare.

The app used to render these server-side with matplotlib/mplsoccer into base64
PNGs. They are now plain JSON "specs" that static/js/charts.js draws as SVG in
one consistent style (theme-aware, hover tooltips, clickable legends, sharp at
any size). Dropping matplotlib also removes ~150MB of imports and a slow first
render from the 512MB free-tier server.

Spec shapes (all have "type"; most have an optional "sub" caption and "stats"
= [[label, value], ...] chips):

  pitch    {view: "full"|"half", guides: [...], layers: [{id,label,color,shape,pts,count,...}]}
           shapes: line/dash take pts [x,y,ex,ey]; dot/ring/star/x/pent take [x,y]
  bars     {items: [{label, value 0-100, color, text}]}
  hist     {counts, edges, unit, color, median, marker?}
  trend    {seasons, values}      rose   {angle, spread}
  bloom    {items: [{label, value, color}], center, center_label}
  scatter  {points, target?, xlabel, ylabel, quads}
  radar    {axes, series: [{name, color, values}]}
  grouped  {cats, series: [{name, color, values}]}
"""
import math
import statistics

import numpy as np

from core.advanced import geometry as g
from core.advanced.geometry import BOX_X_MIN, BOX_Y_MIN, BOX_Y_MAX, HALF_SPACE_Y_LEFT, HALF_SPACE_Y_RIGHT

# ─────────────────────────────────────────────────────────────────────────────
# Shared palette (the JS renderer only ever sees these hex strings)
# ─────────────────────────────────────────────────────────────────────────────
BLUE, GREEN, RED, AMBER, PURPLE, PINK, SLATE, GREY = (
    "#3b82f6", "#22c55e", "#ef4444", "#eab308", "#a855f7", "#ec4899", "#64748b", "#6b7280")

# Same red -> orange -> yellow -> green -> blue gradient as app.js's percentileColor(),
# so a stat's bar colour and its chart colour always match.
_PCT_STOPS = [(0, (239, 68, 68)), (25, (249, 115, 22)), (50, (234, 179, 8)), (75, (34, 197, 94)), (100, (59, 130, 246))]


def percentile_color(pct: float) -> str:
    pct = max(0, min(100, pct))
    for (t0, c0), (t1, c1) in zip(_PCT_STOPS, _PCT_STOPS[1:]):
        if t0 <= pct <= t1:
            a = (pct - t0) / (t1 - t0)
            return "#{:02x}{:02x}{:02x}".format(*(round(c0[i] + a * (c1[i] - c0[i])) for i in range(3)))
    return BLUE


def _share(n: int, total: int) -> int:
    return round(100 * n / total) if total else 0


def _r(v, d=1):
    return None if v is None or v != v else round(float(v), d)   # v != v: NaN -> null (NaN isn't valid JSON)


def _ok(*vals) -> bool:
    return all(v is not None and v == v for v in vals)


# ─────────────────────────────────────────────────────────────────────────────
# Generic builders
# ─────────────────────────────────────────────────────────────────────────────

def bars(items: list, sub: str = None) -> dict:
    """items: (label, bar_value_0_100, colour, display_text)."""
    return {"type": "bars", "sub": sub, "items": [
        {"label": l, "value": round(max(0.0, min(100.0, v)), 1), "color": c, "text": t} for l, v, c, t in items]}


def count_bars(rows: list, total: int = None, sub: str = None) -> dict:
    """rows: (label, count, colour) -> 'count (pct%)' bars, length = share of total."""
    total = sum(r[1] for r in rows) if total is None else total
    return bars([(l, 100 * n / total if total else 0, c, f"{n} ({_share(n, total)}%)") for l, n, c in rows], sub)


def stat_bars(stats: list, labels, sub: str = None, with_pct: bool = False) -> dict:
    """Bars straight from the stat card's own percentile rows."""
    by_label = {s["label"]: s for s in stats}
    items = []
    for label in labels:
        s = by_label.get(label)
        if not s or s.get("no_data"):
            items.append((label, 0, "#374151", "-"))
            continue
        pct = s["percentile"]
        text = f"{s['value']}{s.get('unit', '')}" + (f" ({pct}th pct)" if with_pct else "")
        items.append((label, pct, percentile_color(pct), text))
    return bars(items, sub)


def hist(values: list, bins: int, unit: str = "", color: str = BLUE, marker: tuple = None, sub: str = None) -> dict:
    values = [float(v) for v in values if v is not None]
    if not values:
        return {"type": "hist", "sub": sub, "counts": [], "edges": [], "unit": unit, "color": color}
    counts, edges = np.histogram(values, bins=bins)
    spec = {"type": "hist", "sub": sub, "counts": [int(c) for c in counts], "edges": [round(float(e), 2) for e in edges],
            "unit": unit, "color": color, "median": round(statistics.median(values), 2), "n": len(values)}
    if marker is not None:
        spec["marker"] = {"value": round(float(marker[0]), 2), "label": marker[1]}
    return spec


def layer(id, label, color, shape, pts, count=None, z=None, **kw) -> dict:
    out = {"id": id, "label": label, "color": color, "shape": shape,
           "pts": [[_r(v) for v in p] for p in pts], "count": len(pts) if count is None else count}
    if z is not None:
        out["z"] = z
    out.update(kw)
    return out


def pitch(layers: list, view: str = "full", guides: list = None, stats: list = None, sub: str = None) -> dict:
    return {"type": "pitch", "view": view, "guides": guides or [], "layers": layers, "stats": stats or [], "sub": sub}


def _lines(rows, x="x", y="y", ex="end_x", ey="end_y"):
    return [[r[x], r[y], r[ex], r[ey]] for r in rows if _ok(r[x], r[y], r[ex], r[ey])]


def _dots(rows, x="x", y="y"):
    return [[r[x], r[y]] for r in rows if _ok(r[x], r[y])]


def trend(seasons: list, values: list, sub: str = None) -> dict:
    return {"type": "trend", "sub": sub, "seasons": seasons, "values": [None if v is None else _r(v) for v in values]}


# ─────────────────────────────────────────────────────────────────────────────
# Passing
# ─────────────────────────────────────────────────────────────────────────────
PASS_BOX, PASS_PROG, PASS_OK, PASS_BAD = BLUE, GREEN, SLATE, "#374151"
THIRD_COLORS = {"def": BLUE, "mid": AMBER, "att": GREEN}
THIRD_LABELS = {"def": "Defensive Third", "mid": "Middle Third", "att": "Attacking Third"}


def _pass_bucket(p: dict) -> str:
    if p["into_box"]:
        return "box"
    if p["progressive"]:
        return "prog"
    return "ok" if p["completed"] else "bad"


def passing_map(passes: list, mode: str = "progressive") -> dict:
    buckets = {"box": [], "prog": [], "ok": [], "bad": []}
    counts = dict.fromkeys(buckets, 0)
    for p in passes:
        if not _ok(p["x"], p["y"], p["end_x"], p["end_y"]):
            continue
        b = _pass_bucket(p)
        counts[b] += 1
        if mode == "progressive" and not (p["progressive"] or p["into_box"]):
            continue
        buckets[b].append([p["x"], p["y"], p["end_x"], p["end_y"]])
    layers = [
        layer("box", "Into box", PASS_BOX, "line", buckets["box"], counts["box"], z=4, width=3.2),
        layer("prog", "Progressive", PASS_PROG, "line", buckets["prog"], counts["prog"], z=3, width=2.8),
        layer("ok", "Completed", PASS_OK, "line", buckets["ok"], counts["ok"], z=2, width=2),
        layer("bad", "Unsuccessful", PASS_BAD, "line", buckets["bad"], counts["bad"], z=1, width=1.6),
    ]
    return pitch(layers, stats=[["Passes", len(passes)], ["Progressive", counts["prog"]], ["Into box", counts["box"]]])


def _subset_note(n: int, of: int) -> str:
    return f"{n} progressive and into-box passes, out of {of} passes in all"


def pass_outcomes(passes: list, of: int | None = None) -> dict:
    """`of` is the player's total pass count when `passes` is only the progressive / into-box
    subset (the default view). Every pass in that subset is one or the other, so splitting it
    into Completed / Unsuccessful 'other' passes would show two empty bars; instead each kind
    is split by how the pass ended."""
    n = len(passes)
    if of is not None:
        box = [p for p in passes if p["into_box"]]
        prog = [p for p in passes if p["progressive"] and not p["into_box"]]
        rows = [("Into box, completed", sum(1 for p in box if p["completed"]), PASS_BOX),
                ("Into box, missed", sum(1 for p in box if not p["completed"]), PASS_BAD),
                ("Progressive, completed", sum(1 for p in prog if p["completed"]), PASS_PROG),
                ("Progressive, missed", sum(1 for p in prog if not p["completed"]), PASS_BAD)]
        return count_bars(rows, n, sub=_subset_note(n, of))
    box = sum(1 for p in passes if p["into_box"])
    prog = sum(1 for p in passes if p["progressive"] and not p["into_box"])
    ok = sum(1 for p in passes if p["completed"] and not p["progressive"] and not p["into_box"])
    return count_bars([("Into box", box, PASS_BOX), ("Progressive", prog, PASS_PROG), ("Completed", ok, PASS_OK),
                       ("Unsuccessful", n - box - prog - ok, PASS_BAD)], n, sub=f"All {n} passes")


def release_times(passes: list, of: int | None = None) -> dict:
    values = [p["release_s"] for p in passes if p.get("release_s") is not None]
    sub = f"Sample: {len(values)} passes" if of is None else f"Sample: {len(values)} of the {len(passes)} progressive and into-box passes"
    return hist(values, 14, "s", PASS_OK, sub=sub)


def _by_third(rows: list, sub_fmt: str) -> dict:
    counts = {"def": 0, "mid": 0, "att": 0}
    for r in rows:
        if r["x"] is not None:
            counts[g.zone_third(r["x"])] += 1
    n = sum(counts.values())
    return count_bars([(THIRD_LABELS[z], counts[z], THIRD_COLORS[z]) for z in ("def", "mid", "att")], n, sub=sub_fmt.format(n=n))


def pass_zones(passes: list, of: int | None = None) -> dict:
    return _by_third(passes, "Total: {n}" if of is None else _subset_note("{n}", of))


# ─────────────────────────────────────────────────────────────────────────────
# Shooting
# ─────────────────────────────────────────────────────────────────────────────
GOAL_C, ON_T, OFF_T, HEAD_C, RIGHT_C, LEFT_C = AMBER, BLUE, GREY, PURPLE, BLUE, GREEN


def shot_map(shots: list) -> dict:
    by = {"goal": [], "on_target": [], "off_target": []}
    for s in shots:
        if _ok(s["x"], s["y"]):
            by.setdefault(s["outcome"], by["off_target"]).append([s["x"], s["y"]])
    n = len(shots)
    goals = len(by["goal"])
    layers = [
        layer("goal", "Goals", GOAL_C, "star", by["goal"], z=3),
        layer("on", "On target", ON_T, "dot", by["on_target"], z=2),
        layer("off", "Off target / blocked", OFF_T, "ring", by["off_target"], z=1),
    ]
    return pitch(layers, view="half", stats=[["Shots", n], ["Goals", goals], ["Conversion", f"{_share(goals, n)}%"]])


def shot_distance(shots: list) -> dict:
    values = [g.units_to_meters(g.dist_to_goal(s["x"], s["y"])) for s in shots if _ok(s["x"], s["y"])]
    return hist(values, 12, "m", ON_T, sub=f"Sample: {len(values)} shots")


def shot_body_parts(shots: list) -> dict:
    counts = {"RightFoot": 0, "LeftFoot": 0, "Head": 0, "Other": 0}
    for s in shots:
        bp = s.get("body_part") or "Other"
        counts[bp if bp in ("RightFoot", "LeftFoot", "Head") else "Other"] += 1
    return count_bars([("Right Foot", counts["RightFoot"], RIGHT_C), ("Left Foot", counts["LeftFoot"], LEFT_C),
                       ("Head", counts["Head"], HEAD_C), ("Other", counts["Other"], GREY)], len(shots),
                      sub=f"Total shots: {len(shots)}")


def shot_funnel(shots: list) -> dict:
    n = len(shots)
    sot = sum(1 for s in shots if s["outcome"] in ("goal", "on_target"))
    goals = sum(1 for s in shots if s["outcome"] == "goal")
    return bars([("Shots", 100, OFF_T, str(n)),
                 ("On Target", 100 * sot / n if n else 0, ON_T, f"{sot} ({_share(sot, n)}%)"),
                 ("Goals", 100 * goals / n if n else 0, GOAL_C, f"{goals} ({_share(goals, n)}%)")])


# ─────────────────────────────────────────────────────────────────────────────
# Carrying
# ─────────────────────────────────────────────────────────────────────────────
CARRY_C, FOLLOW_PASS, TAKEON_WON, TAKEON_LOST = RED, GREEN, BLUE, "#9ca3af"


def carry_map(carries: list, show: tuple = ("prog_pass", "takeon_won", "takeon_lost")) -> tuple:
    lines, ends = [], {"prog_pass": [], "takeon_won": [], "takeon_lost": []}
    counts = dict.fromkeys(ends, 0)
    for c in carries:
        if not c["progressive"] or not _ok(c["start_x"], c["start_y"], c["end_x"], c["end_y"]):
            continue
        lines.append([c["start_x"], c["start_y"], c["end_x"], c["end_y"]])
        f = c.get("followup", "none")
        if f in counts:
            counts[f] += 1
            if f in show:
                ends[f].append([c["end_x"], c["end_y"]])
    layers = [
        layer("carry", "Progressive carries", CARRY_C, "dash", lines, z=1, width=2.6),
        layer("pp", "Prog. pass after", FOLLOW_PASS, "dot", ends["prog_pass"], counts["prog_pass"], z=3, r=8),
        layer("tw", "Take-on won after", TAKEON_WON, "dot", ends["takeon_won"], counts["takeon_won"], z=3, r=8),
        layer("tl", "Take-on lost after", TAKEON_LOST, "dot", ends["takeon_lost"], counts["takeon_lost"], z=3, r=8),
    ]
    stats = {"prog_carries": len(lines), "prog_pass_after": counts["prog_pass"],
             "takeon_won_after": counts["takeon_won"], "takeon_lost_after": counts["takeon_lost"]}
    return pitch(layers), stats


def carry_rose(carries: list) -> tuple:
    angles = []
    for c in carries:
        if not c["progressive"] or not _ok(c["start_x"], c["start_y"], c["end_x"], c["end_y"]):
            continue
        dx = c["end_x"] - c["start_x"]
        toward_center = 1 if c["start_y"] < 50 else -1
        dy = (c["end_y"] - c["start_y"]) * toward_center
        if dx == 0 and dy == 0:
            continue
        angles.append(math.atan2(dy, dx))
    spec = {"type": "rose", "angle": None, "spread": None}
    abi = 0.0
    if angles:
        spec["angle"] = round(math.atan2(sum(math.sin(a) for a in angles), sum(math.cos(a) for a in angles)), 3)
        spec["spread"] = round(max(0.25, min(statistics.pstdev(angles) if len(angles) > 1 else 0.4, 1.1)), 3)
        abi = round(sum(math.sin(a) for a in angles) / len(angles), 2)
    label = "infield" if abi > 0.05 else ("outfield" if abi < -0.05 else "neutral")
    return spec, {"abi": abi, "abi_label": label}


def carry_distance(carries: list) -> dict:
    values = []
    for c in carries:
        if _ok(c["start_x"], c["start_y"], c["end_x"], c["end_y"]):
            d = ((c["end_x"] - c["start_x"]) ** 2 + (c["end_y"] - c["start_y"]) ** 2) ** 0.5
            values.append(d / 100.0 * 105.0)   # pitch units -> metres, same as geometry.units_to_meters
    return hist(values, 12, "m", CARRY_C, sub=f"Sample: {len(values)} carries")


def takeon_map(takeons: list) -> dict:
    won = _dots([t for t in takeons if t["outcome"] == "won"])
    lost = _dots([t for t in takeons if t["outcome"] != "won"])
    n = len(won) + len(lost)
    layers = [layer("won", "Won", TAKEON_WON, "dot", won, z=2, r=8), layer("lost", "Lost", TAKEON_LOST, "ring", lost, z=1)]
    return pitch(layers, stats=[["Won", len(won)], ["Lost", len(lost)], ["Success", f"{_share(len(won), n)}%"]])


# ─────────────────────────────────────────────────────────────────────────────
# Aerial
# ─────────────────────────────────────────────────────────────────────────────
WON_C, LOST_C = BLUE, RED


def aerial_map(duels: list, phases: tuple = ("open_play", "set_piece")) -> dict:
    won = _dots([d for d in duels if d["won"] and d["phase"] in phases])
    lost = _dots([d for d in duels if not d["won"] and d["phase"] in phases])
    n = len(won) + len(lost)
    layers = [layer("won", "Aerial won", WON_C, "x", won, z=2), layer("lost", "Aerial lost", LOST_C, "x", lost, z=1)]
    return pitch(layers, stats=[["Won", len(won)], ["Lost", len(lost)], ["Win rate", f"{_share(len(won), n)}%"]])


def aerial_outcomes(stats: list) -> dict:
    return stat_bars(stats, ("Retains & plays", "Falls to teammate", "Falls to opponent", "Cleared out of play"))


def aerial_phases(stats: list, phases: tuple = ("open_play", "set_piece")) -> dict:
    names = {"open_play": "Win rate, open play", "set_piece": "Win rate, set piece"}
    return stat_bars(stats, tuple(names[p] for p in ("open_play", "set_piece") if p in phases))


# ─────────────────────────────────────────────────────────────────────────────
# Hold-up
# ─────────────────────────────────────────────────────────────────────────────
HOLD_STYLE = {
    "prog_release": (GREEN, "Progressive release"), "retained": (BLUE, "Retained"),
    "shot_from_hold": (AMBER, "Shot from hold"), "dangerous_loss": (RED, "Dangerous loss"), "lost": (GREY, "Lost"),
}
HOLD_ZONES = {"final": GREEN, "middle": AMBER, "defensive": BLUE}


def holdup_map(episodes: list) -> dict:
    by = {k: [] for k in HOLD_STYLE}
    for ep in episodes:
        if _ok(ep["x"], ep["y"]):
            by.setdefault(ep["outcome"], by["lost"]).append([ep["x"], ep["y"]])
    n = len(episodes)
    kept = n - len(by["lost"]) - len(by["dangerous_loss"])
    layers = [layer(k, lbl, col, "dot", by[k]) for k, (col, lbl) in HOLD_STYLE.items()]
    return pitch(layers, stats=[["Episodes", n], ["Retention", f"{_share(kept, n)}%"]])


def holdup_outcomes(episodes: list) -> dict:
    counts = {k: 0 for k in HOLD_STYLE}
    for ep in episodes:
        counts[ep["outcome"]] = counts.get(ep["outcome"], 0) + 1
    return count_bars([(lbl, counts[k], col) for k, (col, lbl) in HOLD_STYLE.items()], len(episodes),
                      sub=f"Episodes: {len(episodes)}")


def holdup_zones(all_episodes: list) -> dict:
    counts = {"final": 0, "middle": 0, "defensive": 0}
    for ep in all_episodes:
        counts[ep["zone"]] = counts.get(ep["zone"], 0) + 1
    labels = {"final": "Final Third", "middle": "Middle Third", "defensive": "Defensive Third"}
    n = sum(counts.values())
    return count_bars([(labels[z], counts[z], HOLD_ZONES[z]) for z in ("final", "middle", "defensive")], n, sub=f"Total: {n}")


# ─────────────────────────────────────────────────────────────────────────────
# Half-spaces
# ─────────────────────────────────────────────────────────────────────────────
HS_OFF = {"prog_pass": (GREEN, "Prog. Passes", False), "pass": (BLUE, "Passes", False),
          "unsuccessful": (GREY, "Unsuccessful", False), "prog_carry": (RED, "Prog. Carries", True),
          "carry": ("#f97316", "Carries", True)}
HS_DEF = {"tackle": (GREEN, "Tackles"), "interception": (AMBER, "Interceptions"), "recovery": (BLUE, "Recoveries"),
          "block": (PURPLE, "Blocks"), "aerial": (PINK, "Aerials won")}
HS_LEFT, HS_RIGHT = "#8b5cf6", PINK


def half_space_map(offense: list, defense: list, mode: str = "offensive") -> dict:
    guides = [{"kind": "rect", "x0": 50, "x1": 100, "y0": y0, "y1": y1, "fill": "#8b5cf6", "opacity": 0.14}
              for y0, y1 in (HALF_SPACE_Y_LEFT, HALF_SPACE_Y_RIGHT)]
    layers, off_n = [], {}
    if mode in ("offensive", "both"):
        for k, (col, lbl, dashed) in HS_OFF.items():
            rows = [r for r in offense if r["kind"] == k]
            pts = _lines(rows)
            off_n[k] = len(pts)
            layers.append(layer(k, lbl, col, "dash" if dashed else "line", pts, z=1, width=2.4))
    def_n = 0
    if mode in ("defensive", "both"):
        for k, (col, lbl) in HS_DEF.items():
            pts = _dots([r for r in defense if r["kind"] == k])
            def_n += len(pts)
            if pts or mode == "defensive":
                layers.append(layer(k, lbl, col, "x", pts, z=3))
    if mode == "offensive":
        stats = [["Passes", off_n.get("pass", 0) + off_n.get("prog_pass", 0)], ["Progressive", off_n.get("prog_pass", 0)]]
    elif mode == "defensive":
        stats = [["Actions", def_n]]
    else:
        stats = []
    return pitch(layers, guides=guides, stats=stats)


def half_space_sides(offense: list, defense: list) -> dict:
    rows = offense + defense
    left = sum(1 for r in rows if r["y"] is not None and r["y"] < 50)
    right = sum(1 for r in rows if r["y"] is not None and r["y"] >= 50)
    return count_bars([("Left half-space", left, HS_LEFT), ("Right half-space", right, HS_RIGHT)], left + right,
                      sub=f"Total involvements: {left + right}")


def half_space_percentiles(stats: list, mode: str = "offensive") -> dict:
    off, dfn = ("Progression rate", "Take-on success"), ("Tackle success", "Interceptions", "Recoveries")
    wanted = off if mode == "offensive" else dfn if mode == "defensive" else off + dfn
    return stat_bars(stats, wanted, with_pct=True)


# ─────────────────────────────────────────────────────────────────────────────
# Tempo
# ─────────────────────────────────────────────────────────────────────────────
TEMPO = {"injector_pass": (RED, "Injector Pass", False), "injector_carry": (GREEN, "Injector Carry", True),
         "reset_pass": (BLUE, "Reset Pass", False)}


def tempo_map(actions: list) -> dict:
    layers = [layer(k, lbl, col, "dash" if dashed else "line", _lines([a for a in actions if a["kind"] == k]), width=2.3)
              for k, (col, lbl, dashed) in TEMPO.items()]
    inj = layers[0]["count"] + layers[1]["count"]
    return pitch(layers, stats=[["Injectors", inj], ["Resets", layers[2]["count"]]])


def tempo_release(actions: list) -> dict:
    values = [a["release_s"] for a in actions if a.get("release_s") is not None]
    return hist(values, 14, "s", BLUE, sub=f"Sample: {len(values)} passes")


def tempo_balance(actions: list) -> dict:
    inj = sum(1 for a in actions if a["kind"] in ("injector_pass", "injector_carry"))
    reset = sum(1 for a in actions if a["kind"] == "reset_pass")
    return count_bars([("Injectors", inj, RED), ("Resets", reset, BLUE)], inj + reset, sub=f"Total: {inj + reset}")


# ─────────────────────────────────────────────────────────────────────────────
# Defending
# ─────────────────────────────────────────────────────────────────────────────
DEF_STYLE = {"tackle_won": (GREEN, "Tackle Won"), "tackle_lost": (GREY, "Tackle Lost"), "interception": (BLUE, "Interception"),
             "block": (AMBER, "Block"), "recovery": (PURPLE, "Recovery"), "clearance": (RED, "Clearance")}
DEF_ZONES = {"box": RED, "channel": AMBER, "flank": BLUE, "other": GREY}


def _def_key(a: dict) -> str:
    if a["action"] == "tackle":
        return "tackle_won" if a["outcome"] == "won" else "tackle_lost"
    return a["action"]


def defending_map(actions: list) -> dict:
    guides = [{"kind": "rect", "x0": 0, "x1": 100 - BOX_X_MIN, "y0": BOX_Y_MIN, "y1": BOX_Y_MAX, "stroke": "#8b5cf6", "opacity": 0.6},
              {"kind": "vline", "x": 35, "stroke": "#8b5cf6", "dash": True, "opacity": 0.55}]
    by = {k: [] for k in DEF_STYLE}
    for a in actions:
        if _ok(a["x"], a["y"]):
            by.setdefault(_def_key(a), by["recovery"]).append([a["x"], a["y"]])
    layers = [layer(k, lbl, col, "dot", by[k]) for k, (col, lbl) in DEF_STYLE.items()]
    return pitch(layers, guides=guides, stats=[["Actions", sum(len(v) for v in by.values())]])


def defending_zones(actions: list) -> dict:
    zones = dict.fromkeys(DEF_ZONES, 0)
    for a in actions:
        if _ok(a["x"], a["y"]):
            zones[g.defensive_zone(a["x"], a["y"])] += 1
    n = sum(zones.values())
    names = {"box": "Box", "channel": "Channel", "flank": "Flank", "other": "Other"}
    return count_bars([(names[z], zones[z], DEF_ZONES[z]) for z in DEF_ZONES], n, sub=f"Total: {n}")


def defending_types(actions: list) -> dict:
    counts = dict.fromkeys(DEF_STYLE, 0)
    for a in actions:
        k = _def_key(a)
        counts[k] = counts.get(k, 0) + 1
    n = sum(counts.values())
    return count_bars([(lbl, counts[k], col) for k, (col, lbl) in DEF_STYLE.items()], n, sub=f"Total: {n}")


# ─────────────────────────────────────────────────────────────────────────────
# Post-recovery
# ─────────────────────────────────────────────────────────────────────────────
REC_C = AMBER
REC_STYLE = {"prog_pass": (GREEN, "Prog. Passes", False), "pass": (BLUE, "Passes", False),
             "prog_carry": (RED, "Prog. Carries", True), "unsuccessful": (GREY, "Unsuccessful", False)}


def post_recovery_map(recoveries: list) -> dict:
    counts = dict.fromkeys(REC_STYLE, 0)
    for r in recoveries:
        if _ok(r["x"], r["y"]):
            counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
    layers = [layer("rec", "Recoveries", REC_C, "dot", _dots(recoveries), z=1, r=4, opacity=0.7)]
    for k, (col, lbl, dashed) in REC_STYLE.items():
        rows = [r for r in recoveries if r["outcome"] == k]
        layers.append(layer(k, lbl, col, "dash" if dashed else "line", _lines(rows), counts[k], z=2, width=2.4))
    n = len(recoveries)
    return pitch(layers, stats=[["Recoveries", n], ["Retention", f"{_share(n - counts['unsuccessful'], n)}%"]])


def post_recovery_outcomes(recoveries: list) -> dict:
    counts = dict.fromkeys(REC_STYLE, 0)
    for r in recoveries:
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
    return count_bars([(lbl, counts[k], col) for k, (col, lbl, _d) in REC_STYLE.items()], len(recoveries),
                      sub=f"Recoveries: {len(recoveries)}")


def post_recovery_zones(recoveries: list) -> dict:
    return _by_third(recoveries, "Total: {n}")


# ─────────────────────────────────────────────────────────────────────────────
# Goalkeeping
# ─────────────────────────────────────────────────────────────────────────────
SAVED_C, CONCEDED_C = BLUE, RED


def gk_map(shots: list) -> dict:
    saved = _dots([s for s in shots if s["outcome"] == "saved"])
    conceded = _dots([s for s in shots if s["outcome"] != "saved"])
    n = len(saved) + len(conceded)
    layers = [layer("saved", "Saved", SAVED_C, "dot", saved, z=1, r=8), layer("conc", "Conceded", CONCEDED_C, "star", conceded, z=2)]
    return pitch(layers, stats=[["Shots faced", n], ["Save rate", f"{_share(len(saved), n)}%"]])


def gk_outcomes(shots: list) -> dict:
    saved = sum(1 for s in shots if s["outcome"] == "saved")
    return count_bars([("Saved", saved, SAVED_C), ("Conceded", len(shots) - saved, CONCEDED_C)], len(shots), sub=f"Faced: {len(shots)}")


def gk_distribution(stats: list) -> dict:
    return stat_bars(stats, ("Distribution accuracy", "Plays short", "Save rate"))


# ─────────────────────────────────────────────────────────────────────────────
# Decision making / Final third
# ─────────────────────────────────────────────────────────────────────────────

def decision_bloom(stats: list) -> dict:
    items = [{"label": s["label"], "value": max(2, s["percentile"]), "color": percentile_color(max(2, s["percentile"]))} for s in stats]
    overall = round(sum(i["value"] for i in items) / len(items)) if items else 0
    return {"type": "bloom", "items": items, "center": overall, "center_label": "DECISION"}


def decision_bars(stats: list) -> dict:
    ordered = sorted(stats, key=lambda s: s["percentile"], reverse=True)
    return bars([(s["label"], s["percentile"], percentile_color(s["percentile"]), f"{s['percentile']}th pct") for s in ordered])


TARGET_C = "#8b5cf6"
PILLARS = {"shooting": ("Shooting", AMBER), "linkup": ("Link-Up", BLUE), "carrying": ("Carrying", RED), "ballwinning": ("Ball Winning", GREEN)}


def final_third_scatter(player_name: str, points: list) -> dict:
    others = [[_r(p["completeness"]), _r(p["impact"])] for p in points if not p["is_target"]]
    target = next((p for p in points if p["is_target"]), None)
    return {"type": "scatter", "points": others,
            "target": {"x": _r(target["completeness"]), "y": _r(target["impact"]), "label": player_name} if target else None,
            "xlabel": "Completeness (floor: sustained all-round involvement)", "ylabel": "Impact (ceiling: damage per touch)",
            "quads": ["MOMENTS PLAYER", "COMPLETE & DECISIVE", "PERIPHERAL", "CONNECTOR"]}


def pillar_bars(floor_pct: dict, per_touch_pct: dict) -> dict:
    items = [(f"{PILLARS[p][0]} (floor)", floor_pct[p], PILLARS[p][1], f"{floor_pct[p]}th pct") for p in PILLARS]
    items += [(f"{PILLARS[p][0]} (per touch)", per_touch_pct[p], PILLARS[p][1], f"{per_touch_pct[p]}th pct") for p in PILLARS]
    return bars(items)


def completeness_distribution(player_name: str, cohort_points: list, player_completeness) -> dict:
    values = [p["completeness"] for p in cohort_points if p.get("completeness") is not None]
    marker = (player_completeness, f"{player_name}: {player_completeness}") if player_completeness is not None else None
    return hist(values, 14, "", SLATE, marker, sub=f"Cohort size: {len(values)}")


# ─────────────────────────────────────────────────────────────────────────────
# Combination play (passer -> receiver)
# ─────────────────────────────────────────────────────────────────────────────
LINK_STYLE = {"prog_pass": (GREEN, "Prog. Passes", False), "pass": (BLUE, "Passes", False),
              "unsuccessful": (GREY, "Unsuccessful", False), "prog_carry": (RED, "Prog. Carries", True)}


def linkup_map(passer_name: str, receptions: list) -> dict:
    counts = {k: 0 for k in (*LINK_STYLE, "takeon_won", "takeon_lost", "shot")}
    lines = {k: [] for k in LINK_STYLE}
    dots = {"takeon_won": [], "takeon_lost": [], "shot": []}
    for r in receptions:
        o = r["outcome"]
        counts[o] = counts.get(o, 0) + 1
        if o in LINK_STYLE and _ok(r.get("end_x"), r.get("end_y")):
            lines[o].append([r["reception_x"], r["reception_y"], r["end_x"], r["end_y"]])
        elif o in dots:
            dots[o].append([r["reception_x"], r["reception_y"]])
    layers = [layer("rec", f"Pass from {passer_name}", AMBER, "dot", [[r["reception_x"], r["reception_y"]] for r in receptions],
                    z=1, r=4, opacity=0.7)]
    for k, (col, lbl, dashed) in LINK_STYLE.items():
        layers.append(layer(k, lbl, col, "dash" if dashed else "line", lines[k], counts[k], z=3, width=2.8))
    layers += [layer("tw", "Take-Ons won", TAKEON_WON, "dot", dots["takeon_won"], z=4, r=8),
               layer("tl", "Take-Ons lost", TAKEON_LOST, "dot", dots["takeon_lost"], z=4, r=8),
               layer("shot", "Shots", PINK, "pent", dots["shot"], z=5)]
    n = len(receptions)
    prog = _share(counts["prog_pass"] + counts["prog_carry"], n)
    return pitch(layers, stats=[["Receptions", n], ["Progresses", f"{prog}%"]])


# ─────────────────────────────────────────────────────────────────────────────
# Compare
# ─────────────────────────────────────────────────────────────────────────────
from core.advanced.composite import category_percentile        # noqa: E402  (kept next to its only users)
from core.advanced.metrics_master import CATEGORY_ORDER        # noqa: E402

PLAYER_COLORS = ["#3b82f6", "#f43f5e", "#10b981", "#f59e0b"]
CATEGORY_LABELS_SHORT = {
    "passing": "Passing", "shooting": "Shooting", "carrying": "Carrying", "half_spaces": "Half-Spaces", "tempo": "Tempo",
    "decision_making": "Decisions", "final_third": "Final Third", "aerial": "Aerial", "defending": "Defending",
    "holdup": "Hold-Up", "post_recovery": "Post-Recovery", "goalkeeping": "Goalkeeping",
}
# (category key, stat label) per radar axis. A player missing that category (e.g. a keeper has no
# Aerial tab) plots 0 on the axis rather than erroring.
RADAR_METRICS = [("passing", "Progressive passes"), ("carrying", "Progressive carries"), ("shooting", "Goals"),
                 ("aerial", "Aerial duels"), ("defending", "Tackles"), ("final_third", "Completeness")]
RADAR_LABELS = ["Prog. Passes", "Prog. Carries", "Goals", "Aerial Duels", "Tackles", "Final Third"]


def _percentile_for(cats: list, cat_key: str, label: str) -> float:
    cat = next((c for c in cats if c["key"] == cat_key), None)
    if not cat:
        return 0.0
    stats = cat["rows"][0]["stats"] if cat.get("rows") else []
    s = next((s for s in stats if s["label"] == label), None)
    return 0.0 if not s or s.get("no_data") else float(s["percentile"])


def compare_radar(players: list) -> dict:
    series = [{"name": p["name"], "color": PLAYER_COLORS[i % 4],
               "values": [_r(_percentile_for(p["cats"], k, l)) for k, l in RADAR_METRICS]} for i, p in enumerate(players)]
    return {"type": "radar", "axes": RADAR_LABELS, "series": series}


def profile_radar(cats: list, name: str) -> dict | None:
    """One player's average percentile in every category, as a radar -- the whole profile at a
    glance. Categories with no usable stat are left off; under three axes it is not a shape."""
    axes, values = [], []
    for c in cats:
        if c.get("key") == "linkup":
            continue
        v = category_percentile(c)
        if v is None:
            continue
        axes.append(CATEGORY_LABELS_SHORT.get(c["key"], c.get("label", c["key"])))
        values.append(_r(v))
    if len(axes) < 3:
        return None
    return {"type": "radar", "sub": "Average percentile in each category, against players in the same position group",
            "axes": axes, "series": [{"name": name, "color": PLAYER_COLORS[0], "values": values}]}


GROUP_COLORS = {"attacker": "#f43f5e", "midfielder": "#10b981", "defender": "#3b82f6", "goalkeeper": "#f59e0b"}


def metric_scatter(points: list, x_label: str, y_label: str, x_unit: str = "", y_unit: str = "",
                   x_invert: bool = False, y_invert: bool = False, sub: str = None) -> dict:
    """Every player-season as a dot on two chosen metrics. points: dicts with x, y, name, team,
    league, season, position, group, id, minutes. Kept small: one array per dot."""
    return {"type": "xy", "sub": sub, "xlabel": x_label, "ylabel": y_label, "xunit": x_unit, "yunit": y_unit,
            "xinvert": x_invert, "yinvert": y_invert, "colors": GROUP_COLORS,
            "points": [[_r(p["x"], 3), _r(p["y"], 3), p["name"], p["team"], p["id"], p["league"], p["season"],
                        p["group"], p["minutes"]] for p in points]}


def compare_composite(players: list) -> dict:
    items = []
    for i, p in enumerate(players):
        score = p["composite"]["score"]
        items.append((p["name"], score if score is not None else 0, PLAYER_COLORS[i % 4], f"{score}" if score is not None else "-"))
    return bars(items, sub="Position-weighted across every category")


def compare_categories(players: list) -> dict:
    present = [k for k in CATEGORY_ORDER if k != "linkup" and any(any(c["key"] == k for c in p["cats"]) for p in players)] or ["passing"]
    series = []
    for i, p in enumerate(players):
        vals = []
        for key in present:
            cat = next((c for c in p["cats"] if c["key"] == key), None)
            pct = category_percentile(cat) if cat else None
            vals.append(_r(pct if pct is not None else 0))
        series.append({"name": p["name"], "color": PLAYER_COLORS[i % 4], "values": vals})
    return {"type": "grouped", "cats": [CATEGORY_LABELS_SHORT.get(k, k) for k in present], "series": series}
