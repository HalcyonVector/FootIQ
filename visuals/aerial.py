"""Aerial Duels — every duel plotted at its location, won vs lost, filtered by phase."""
import matplotlib.pyplot as plt
from mplsoccer import Pitch

from visuals.chart_utils import (
    BG_DARK, BG_PANEL, LINE_COLOR, fig_to_b64, layout_pitch_axes, draw_title,
    generate_stat_bar_chart, percentile_color,
)

WON_COLOR = "#3b82f6"
LOST_COLOR = "#ef4444"


def generate_aerial_chart(player_name: str, team: str, season: str, duels: list[dict],
                           phases: tuple = ("open_play", "set_piece")) -> str:
    pitch = Pitch(pitch_type="opta", pitch_color=BG_PANEL, line_color=LINE_COLOR, linewidth=1.2, half=False)
    fig, ax = pitch.draw(figsize=(11, 7.3))
    fig.set_facecolor(BG_DARK)
    layout_pitch_axes(ax, top=0.80, bottom=0.11)

    won_n = lost_n = 0
    for d in duels:
        if d["x"] is None or d["y"] is None or d["phase"] not in phases:
            continue
        if d["won"]:
            won_n += 1
            pitch.scatter(d["x"], d["y"], ax=ax, marker="X", color=WON_COLOR, s=70, zorder=4,
                          edgecolors="white", linewidth=0.4)
        else:
            lost_n += 1
            pitch.scatter(d["x"], d["y"], ax=ax, marker="X", color=LOST_COLOR, s=55, zorder=3, alpha=0.85)

    n = won_n + lost_n
    win_pct = round(100 * won_n / n) if n else 0
    subtitle = f"Aerial Duel Locations | {team} | {season}    Won: {won_n}    Lost: {lost_n}    Win rate: {win_pct}%"
    draw_title(fig, player_name, subtitle)

    handles = [plt.Line2D([0], [0], marker="X", color="none", markerfacecolor=c, markersize=10, markeredgecolor="white")
               for c in (WON_COLOR, LOST_COLOR)]
    fig.legend(handles, [f"Aerial Won: {won_n}", f"Aerial Lost: {lost_n}"], loc="lower center", ncol=2,
               frameon=False, labelcolor="#cbd5e1", fontsize=8.5, bbox_to_anchor=(0.5, 0.02))
    return fig_to_b64(fig)


def _stat_bar_from_labels(title, subtitle, stats, labels):
    by_label = {s["label"]: s for s in stats}
    items = []
    for label in labels:
        s = by_label.get(label)
        if not s or s.get("no_data"):
            items.append((label, 0, "#374151", "-"))
            continue
        pct = s["percentile"]
        items.append((label, pct, percentile_color(pct), f"{s['value']}{s.get('unit','')}"))
    return generate_stat_bar_chart(title, subtitle, items)


def generate_aerial_outcome_chart(player_name: str, team: str, season: str, stats: list[dict]) -> str:
    """What happens after this player WINS a duel — retains it themselves,
    lays it to a teammate, or immediately loses it back — read straight off
    the stat card's own outcome-trace percentiles."""
    labels = ("Retains & plays", "Falls to teammate", "Falls to opponent", "Cleared out of play")
    return _stat_bar_from_labels("Outcome After Winning a Duel", f"{team} | {season}", stats, labels)


def generate_aerial_phase_chart(player_name: str, team: str, season: str, stats: list[dict],
                                 phases: tuple = ("open_play", "set_piece")) -> str:
    """Open-play vs set-piece win rate — a player can be dominant at corners
    and mediocre in open-play duels, or vice versa. Only shows whichever
    phase(s) are currently checked on the map's own phase filter, so this
    doesn't just sit static while the map above it changes."""
    phase_labels = {"open_play": "Win rate, open play", "set_piece": "Win rate, set piece"}
    labels = tuple(phase_labels[p] for p in ("open_play", "set_piece") if p in phases)
    return _stat_bar_from_labels("Win Rate by Phase", f"{team} | {season}", stats, labels)
