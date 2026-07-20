"""Hold-Up Play — one marker per episode (5s+ holds), colored by outcome.
`zone` picks which of the reference's three views to render: final third
(default), middle third, or the whole pitch."""
import matplotlib.pyplot as plt
from mplsoccer import Pitch

from visuals.chart_utils import BG_DARK, BG_PANEL, LINE_COLOR, fig_to_b64, layout_pitch_axes, draw_title, generate_stat_bar_chart

OUTCOME_STYLE = {
    "prog_release":  {"color": "#22c55e", "label": "Progressive release"},
    "retained":      {"color": "#3b82f6", "label": "Retained"},
    "shot_from_hold": {"color": "#eab308", "label": "Shot from hold"},
    "dangerous_loss": {"color": "#ef4444", "label": "Dangerous loss"},
    "lost":          {"color": "#6b7280", "label": "Lost"},
}
ZONE_LABELS = {"final": "Final Third", "middle": "Middle Third", "whole": "Whole Pitch"}


def generate_holdup_chart(player_name: str, team: str, season: str, episodes: list[dict], zone: str = "final") -> str:
    pitch = Pitch(pitch_type="opta", pitch_color=BG_PANEL, line_color=LINE_COLOR, linewidth=1.2, half=False)
    fig, ax = pitch.draw(figsize=(11, 7.3))
    fig.set_facecolor(BG_DARK)
    layout_pitch_axes(ax, top=0.80, bottom=0.13)

    counts = {k: 0 for k in OUTCOME_STYLE}
    for ep in episodes:
        if ep["x"] is None or ep["y"] is None:
            continue
        style = OUTCOME_STYLE.get(ep["outcome"], OUTCOME_STYLE["lost"])
        counts[ep["outcome"]] = counts.get(ep["outcome"], 0) + 1
        pitch.scatter(ep["x"], ep["y"], ax=ax, color=style["color"], s=60, zorder=3,
                      edgecolors="white", linewidth=0.4, alpha=0.85)

    n = len(episodes)
    ret_pct = round(100 * (n - counts.get("lost", 0) - counts.get("dangerous_loss", 0)) / n) if n else 0
    zone_label = ZONE_LABELS.get(zone, "Final Third")
    subtitle = f"Hold-Up Episodes | {zone_label} | {team} | {season}    Episodes: {n}    Retention: {ret_pct}%"
    draw_title(fig, player_name, subtitle)

    handles = [plt.Line2D([0], [0], marker="o", color="none", markerfacecolor=v["color"], markersize=9, markeredgecolor="white")
               for v in OUTCOME_STYLE.values()]
    labels = [f"{v['label']}: {counts.get(k,0)}" for k, v in OUTCOME_STYLE.items()]
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False,
               labelcolor="#cbd5e1", fontsize=8, bbox_to_anchor=(0.5, 0.02))
    return fig_to_b64(fig)


def generate_holdup_outcome_chart(player_name: str, team: str, season: str, episodes: list[dict]) -> str:
    """Outcome share for the CURRENTLY selected zone's episodes — retained,
    progressive release, shot from hold, dangerous loss, or plain lost."""
    n = len(episodes)
    counts = {k: 0 for k in OUTCOME_STYLE}
    for ep in episodes:
        counts[ep["outcome"]] = counts.get(ep["outcome"], 0) + 1
    items = [(v["label"], 100 * counts[k] / n if n else 0, v["color"], f"{counts[k]} ({round(100*counts[k]/n) if n else 0}%)")
              for k, v in OUTCOME_STYLE.items()]
    return generate_stat_bar_chart("Hold-Up Outcome Breakdown", f"{team} | {season}    Episodes: {n}", items)


ZONE_COLORS = {"final": "#22c55e", "middle": "#eab308", "defensive": "#3b82f6"}


def generate_holdup_zone_volume_chart(player_name: str, team: str, season: str, all_episodes: list[dict]) -> str:
    """Episode VOLUME split across final/middle/defensive third — pass the
    FULL unfiltered episode list here (not the zone-filtered one used for the
    map), since the whole point is comparing across zones."""
    counts = {"final": 0, "middle": 0, "defensive": 0}
    for ep in all_episodes:
        counts[ep["zone"]] = counts.get(ep["zone"], 0) + 1
    n = sum(counts.values())
    labels = {"final": "Final Third", "middle": "Middle Third", "defensive": "Defensive Third"}
    items = [(labels[z], 100 * counts[z] / n if n else 0, ZONE_COLORS[z], f"{counts[z]} ({round(100*counts[z]/n) if n else 0}%)")
              for z in ("final", "middle", "defensive")]
    return generate_stat_bar_chart("Episodes by Zone", f"{team} | {season}    Total: {n}", items)
