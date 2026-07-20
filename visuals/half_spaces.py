"""
Half-Spaces — the two shaded strips between the box edge and the touchline
in the attacking half. `mode` picks Offensive (pass/carry vectors, green =
progressive), Defensive (action dots), or Both.
"""
import matplotlib.pyplot as plt
from mplsoccer import Pitch

from core.advanced.geometry import HALF_SPACE_Y_LEFT, HALF_SPACE_Y_RIGHT
from visuals.chart_utils import (
    BG_DARK, BG_PANEL, LINE_COLOR, fig_to_b64, layout_pitch_axes, draw_title,
    generate_stat_bar_chart, percentile_color,
)

OFF_STYLE = {
    "prog_pass":   {"color": "#22c55e", "label": "Prog. Passes"},
    "pass":        {"color": "#3b82f6", "label": "Passes"},
    "unsuccessful": {"color": "#6b7280", "label": "Unsuccessful"},
    "prog_carry":  {"color": "#ef4444", "label": "Prog. Carries", "dashed": True},
    "carry":       {"color": "#f97316", "label": "Carries", "dashed": True},
}
DEF_STYLE = {
    "tackle":       {"color": "#22c55e", "label": "Tackles"},
    "interception": {"color": "#eab308", "label": "Interceptions"},
    "recovery":     {"color": "#3b82f6", "label": "Recoveries"},
    "block":        {"color": "#a855f7", "label": "Blocks"},
    "aerial":       {"color": "#ec4899", "label": "Aerials won"},
}


def _shade_half_spaces(ax):
    for y0, y1 in (HALF_SPACE_Y_LEFT, HALF_SPACE_Y_RIGHT):
        ax.axhspan(y0, y1, xmin=0.5, xmax=1.0, color="#8b5cf6", alpha=0.12, zorder=0)


def generate_half_space_chart(player_name: str, team: str, season: str,
                               offense: list[dict], defense: list[dict], mode: str = "offensive") -> str:
    pitch = Pitch(pitch_type="opta", pitch_color=BG_PANEL, line_color=LINE_COLOR, linewidth=1.2, half=False)
    fig, ax = pitch.draw(figsize=(11, 7.3))
    fig.set_facecolor(BG_DARK)
    layout_pitch_axes(ax, top=0.80, bottom=0.11)
    _shade_half_spaces(ax)

    off_counts = {k: 0 for k in OFF_STYLE}
    def_counts = {k: 0 for k in DEF_STYLE}

    if mode in ("offensive", "both"):
        for r in offense:
            if None in (r["x"], r["y"], r["end_x"], r["end_y"]):
                continue
            style = OFF_STYLE.get(r["kind"])
            if not style:
                continue
            off_counts[r["kind"]] += 1
            pitch.lines(r["x"], r["y"], r["end_x"], r["end_y"], ax=ax, color=style["color"], lw=1.4,
                        linestyle="--" if style.get("dashed") else "-", alpha=0.75, zorder=2)

    if mode in ("defensive", "both"):
        for r in defense:
            if r["x"] is None or r["y"] is None:
                continue
            style = DEF_STYLE.get(r["kind"])
            if not style:
                continue
            def_counts[r["kind"]] += 1
            pitch.scatter(r["x"], r["y"], ax=ax, marker="X", color=style["color"], s=55, zorder=4,
                          edgecolors="white", linewidth=0.3)

    mode_label = {"offensive": "Offensive", "defensive": "Defensive", "both": "Offensive + Defensive"}[mode]
    if mode == "offensive":
        subtitle = f"Half-Space Play | {mode_label} | {team} | {season}    Passes: {off_counts['pass']+off_counts['prog_pass']}    Progressive: {off_counts['prog_pass']}"
    elif mode == "defensive":
        n = sum(def_counts.values())
        subtitle = f"Half-Space Play | {mode_label} | {team} | {season}    Actions: {n}"
    else:
        subtitle = f"Half-Space Play | {mode_label} | {team} | {season}"
    draw_title(fig, player_name, subtitle)

    handles, labels = [], []
    if mode in ("offensive", "both"):
        for k, v in OFF_STYLE.items():
            handles.append(plt.Line2D([0], [0], color=v["color"], lw=2.5, linestyle="--" if v.get("dashed") else "-"))
            labels.append(f"{v['label']}: {off_counts[k]}")
    if mode in ("defensive", "both"):
        for k, v in DEF_STYLE.items():
            if def_counts[k] == 0 and mode == "both":
                continue
            handles.append(plt.Line2D([0], [0], marker="X", color="none", markerfacecolor=v["color"], markersize=8, markeredgecolor="white"))
            labels.append(f"{v['label']}: {def_counts[k]}")
    fig.legend(handles, labels, loc="lower center", ncol=min(len(labels), 4) or 1, frameon=False,
               labelcolor="#cbd5e1", fontsize=7.8, bbox_to_anchor=(0.5, 0.02))
    return fig_to_b64(fig)


LEFT_COLOR = "#8b5cf6"
RIGHT_COLOR = "#ec4899"


def generate_half_space_zone_split_chart(player_name: str, team: str, season: str,
                                          offense: list[dict], defense: list[dict]) -> str:
    """Left-strip vs right-strip share of all half-space involvement (offense
    + defense combined) — is this player's half-space work one-footed/one-sided."""
    left_n = sum(1 for r in offense + defense if r["y"] is not None and r["y"] < 50)
    right_n = sum(1 for r in offense + defense if r["y"] is not None and r["y"] >= 50)
    n = left_n + right_n
    items = [
        ("Left half-space", 100 * left_n / n if n else 0, LEFT_COLOR, f"{left_n} ({round(100*left_n/n) if n else 0}%)"),
        ("Right half-space", 100 * right_n / n if n else 0, RIGHT_COLOR, f"{right_n} ({round(100*right_n/n) if n else 0}%)"),
    ]
    return generate_stat_bar_chart("Half-Space Side Split", f"{team} | {season}    Total involvements: {n}", items)


def generate_half_space_percentile_chart(player_name: str, team: str, season: str, stats: list[dict],
                                          mode: str = "offensive") -> str:
    """Half-space percentiles pulled straight from the stat card — matches
    whichever mode (offensive/defensive/both) the map above it is set to,
    instead of always showing the same fixed set regardless of the toggle."""
    OFFENSIVE_LABELS = ("Progression rate", "Take-on success")
    DEFENSIVE_LABELS = ("Tackle success", "Interceptions", "Recoveries")
    if mode == "offensive":
        wanted = OFFENSIVE_LABELS
    elif mode == "defensive":
        wanted = DEFENSIVE_LABELS
    else:
        wanted = OFFENSIVE_LABELS + DEFENSIVE_LABELS
    by_label = {s["label"]: s for s in stats}
    items = []
    for label in wanted:
        s = by_label.get(label)
        if not s or s.get("no_data"):
            items.append((label, 0, "#374151", "-"))
            continue
        pct = s["percentile"]
        items.append((label, pct, percentile_color(pct), f"{s['value']}{s.get('unit','')} ({pct}th pct)"))
    return generate_stat_bar_chart("Half-Space Percentiles", f"{team} | {season}", items)
