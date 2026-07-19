"""
Defending Profile — every defensive action plotted at its location (already
own-goal-relative, x=0 = this player's own goal — see geometry.defensive_zone).
Own box and the defensive-third line are drawn for zone context.
"""
import matplotlib.pyplot as plt
from mplsoccer import Pitch

from core.advanced import geometry as g
from core.advanced.geometry import BOX_X_MIN, BOX_Y_MIN, BOX_Y_MAX
from visuals.chart_utils import BG_DARK, BG_PANEL, LINE_COLOR, fig_to_b64, layout_pitch_axes, draw_title, generate_stat_bar_chart

STYLE = {
    "tackle_won":   {"color": "#22c55e", "label": "Tackle Won"},
    "tackle_lost":  {"color": "#6b7280", "label": "Tackle Lost"},
    "interception": {"color": "#3b82f6", "label": "Interception"},
    "block":        {"color": "#eab308", "label": "Block"},
    "recovery":     {"color": "#a855f7", "label": "Recovery"},
    "clearance":    {"color": "#ef4444", "label": "Clearance"},
}
DEFENSIVE_THIRD_X = 35.0


def _action_key(a: dict) -> str:
    if a["action"] == "tackle":
        return "tackle_won" if a["outcome"] == "won" else "tackle_lost"
    return a["action"]


def generate_defending_chart(player_name: str, team: str, season: str, actions: list[dict]) -> str:
    pitch = Pitch(pitch_type="opta", pitch_color=BG_PANEL, line_color=LINE_COLOR, linewidth=1.2, half=False)
    fig, ax = pitch.draw(figsize=(11, 7.3))
    fig.set_facecolor(BG_DARK)
    layout_pitch_axes(ax, top=0.80, bottom=0.13)

    own_box_x1 = 100 - BOX_X_MIN
    ax.add_patch(plt.Rectangle((0, BOX_Y_MIN), own_box_x1, BOX_Y_MAX - BOX_Y_MIN,
                                fill=False, edgecolor="#8b5cf6", linewidth=1.2, alpha=0.6, zorder=1))
    ax.axvline(DEFENSIVE_THIRD_X, color="#8b5cf6", linewidth=1, linestyle=":", alpha=0.5, zorder=1)

    counts = {k: 0 for k in STYLE}
    for a in actions:
        if a["x"] is None or a["y"] is None:
            continue
        key = _action_key(a)
        style = STYLE.get(key, STYLE["recovery"])
        counts[key] = counts.get(key, 0) + 1
        pitch.scatter(a["x"], a["y"], ax=ax, color=style["color"], s=45, zorder=3, alpha=0.85,
                      edgecolors="white", linewidth=0.3)

    n = sum(counts.values())
    subtitle = f"Defensive Actions | {team} | {season}    Actions: {n}"
    draw_title(fig, player_name, subtitle)

    handles = [plt.Line2D([0], [0], marker="o", color="none", markerfacecolor=v["color"], markersize=8, markeredgecolor="white")
               for v in STYLE.values()]
    labels = [f"{v['label']}: {counts[k]}" for k, v in STYLE.items()]
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False,
               labelcolor="#cbd5e1", fontsize=8, bbox_to_anchor=(0.5, 0.02))
    return fig_to_b64(fig)


ZONE_COLORS = {"box": "#ef4444", "channel": "#eab308", "flank": "#3b82f6", "other": "#6b7280"}


def generate_defending_zone_chart(player_name: str, team: str, season: str, actions: list[dict]) -> str:
    """Box vs channel vs flank vs other-zone share of all defensive actions —
    the same zone split Defending Profile's own stat rows are organized by."""
    zones = {"box": 0, "channel": 0, "flank": 0, "other": 0}
    for a in actions:
        if a["x"] is None or a["y"] is None:
            continue
        zones[g.defensive_zone(a["x"], a["y"])] += 1
    n = sum(zones.values())
    labels = {"box": "Box", "channel": "Channel", "flank": "Flank", "other": "Other"}
    items = [(labels[z], 100 * zones[z] / n if n else 0, ZONE_COLORS[z], f"{zones[z]} ({round(100*zones[z]/n) if n else 0}%)")
              for z in ("box", "channel", "flank", "other")]
    return generate_stat_bar_chart("Defensive Actions by Zone", f"{team} | {season}    Total: {n}", items)


def generate_defending_type_chart(player_name: str, team: str, season: str, actions: list[dict]) -> str:
    """Action-type share — tackles won/lost, interceptions, blocks,
    clearances, recoveries, aerials — same buckets/colors as the map's own legend."""
    counts = {k: 0 for k in STYLE}
    for a in actions:
        counts[_action_key(a)] = counts.get(_action_key(a), 0) + 1
    n = sum(counts.values())
    items = [(v["label"], 100 * counts[k] / n if n else 0, v["color"], f"{counts[k]} ({round(100*counts[k]/n) if n else 0}%)")
              for k, v in STYLE.items()]
    return generate_stat_bar_chart("Action-Type Breakdown", f"{team} | {season}    Total: {n}", items)
