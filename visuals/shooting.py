"""
Shooting & Footedness shot map — every open-play shot plotted at its
location, star markers for goals, circle for on-target saves, hollow ring
for off-target attempts.
"""
import matplotlib.pyplot as plt
from mplsoccer import Pitch

from core.advanced import geometry as g
from visuals.chart_utils import (
    BG_DARK, BG_PANEL, LINE_COLOR, fig_to_b64, layout_pitch_axes, draw_title,
    generate_stat_bar_chart, generate_histogram_chart,
)

GOAL_COLOR = "#eab308"
ON_TARGET_COLOR = "#3b82f6"
OFF_TARGET_COLOR = "#6b7280"
HEAD_COLOR = "#a855f7"
RIGHT_FOOT_COLOR = "#3b82f6"
LEFT_FOOT_COLOR = "#22c55e"
OTHER_BODY_COLOR = "#6b7280"


def generate_shooting_chart(player_name: str, team: str, season: str, shots: list[dict]) -> str:
    pitch = Pitch(pitch_type="opta", pitch_color=BG_PANEL, line_color=LINE_COLOR, linewidth=1.2, half=True)
    fig, ax = pitch.draw(figsize=(8.5, 7.6))
    fig.set_facecolor(BG_DARK)
    layout_pitch_axes(ax, top=0.80, bottom=0.11)

    counts = {"goal": 0, "on_target": 0, "off_target": 0}
    for s in shots:
        if s["x"] is None or s["y"] is None:
            continue
        counts[s["outcome"]] = counts.get(s["outcome"], 0) + 1
        if s["outcome"] == "goal":
            pitch.scatter(s["x"], s["y"], ax=ax, color=GOAL_COLOR, s=140, marker="*", zorder=5,
                          edgecolors="white", linewidth=0.6)
        elif s["outcome"] == "on_target":
            pitch.scatter(s["x"], s["y"], ax=ax, color=ON_TARGET_COLOR, s=55, zorder=4,
                          edgecolors="white", linewidth=0.4)
        else:
            pitch.scatter(s["x"], s["y"], ax=ax, facecolors="none", edgecolors=OFF_TARGET_COLOR, s=45,
                          linewidth=1.1, zorder=3)

    n = len(shots)
    conv = round(100 * counts["goal"] / n) if n else 0
    subtitle = f"Shot Map | {team} | {season}    Shots: {n}    Goals: {counts['goal']}    Conversion: {conv}%"
    draw_title(fig, player_name, subtitle)

    handles = [
        plt.Line2D([0], [0], marker="*", color="none", markerfacecolor=GOAL_COLOR, markersize=13, markeredgecolor="white"),
        plt.Line2D([0], [0], marker="o", color="none", markerfacecolor=ON_TARGET_COLOR, markersize=9, markeredgecolor="white"),
        plt.Line2D([0], [0], marker="o", color="none", markerfacecolor="none", markersize=9, markeredgecolor=OFF_TARGET_COLOR),
    ]
    labels = [f"Goals: {counts['goal']}", f"On target: {counts['on_target']}", f"Off target: {counts['off_target']}"]
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False,
               labelcolor="#cbd5e1", fontsize=8.5, bbox_to_anchor=(0.5, 0.02))
    return fig_to_b64(fig)


def generate_shot_distance_chart(player_name: str, team: str, season: str, shots: list[dict]) -> str:
    """Distribution of shot distance-to-goal (meters) — is this player mostly
    a close-range finisher or a shoot-from-anywhere profile."""
    values = [g.units_to_meters(g.dist_to_goal(s["x"], s["y"])) for s in shots if s["x"] is not None and s["y"] is not None]
    return generate_histogram_chart("Shot Distance Distribution", f"{team} | {season}    Sample: {len(values)} shots",
                                     values, bins=12, unit="m", color=ON_TARGET_COLOR)


def generate_body_part_chart(player_name: str, team: str, season: str, shots: list[dict]) -> str:
    """Footedness/body-part breakdown — same body-part qualifiers the stat
    card's weak-foot metrics read, just shown as shot-share here."""
    n = len(shots)
    counts = {"RightFoot": 0, "LeftFoot": 0, "Head": 0, "Other": 0}
    for s in shots:
        bp = s.get("body_part") or "Other"
        counts[bp if bp in ("RightFoot", "LeftFoot", "Head") else "Other"] += 1

    style = [("RightFoot", "Right Foot", RIGHT_FOOT_COLOR), ("LeftFoot", "Left Foot", LEFT_FOOT_COLOR),
             ("Head", "Head", HEAD_COLOR), ("Other", "Other", OTHER_BODY_COLOR)]
    items = [(label, 100 * counts[key] / n if n else 0, color, f"{counts[key]} ({round(100*counts[key]/n) if n else 0}%)")
             for key, label, color in style]
    return generate_stat_bar_chart("Shots by Body Part", f"{team} | {season}    Total shots: {n}", items)


def generate_shot_funnel_chart(player_name: str, team: str, season: str, shots: list[dict]) -> str:
    """Shots -> on target -> goals conversion funnel."""
    n = len(shots)
    sot = sum(1 for s in shots if s["outcome"] in ("goal", "on_target"))
    goals = sum(1 for s in shots if s["outcome"] == "goal")
    items = [
        ("Shots", 100, OFF_TARGET_COLOR, str(n)),
        ("On Target", 100 * sot / n if n else 0, ON_TARGET_COLOR, f"{sot} ({round(100*sot/n) if n else 0}%)"),
        ("Goals", 100 * goals / n if n else 0, GOAL_COLOR, f"{goals} ({round(100*goals/n) if n else 0}%)"),
    ]
    return generate_stat_bar_chart("Shot Conversion Funnel", f"{team} | {season}", items)
