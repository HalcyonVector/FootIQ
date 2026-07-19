"""
Goalkeeping — every shot faced plotted at its location (normalized to the
keeper's own goal, x=0 — see chart_events.extract_goalkeeping for the
Goal-event coordinate flip), split into saved vs conceded.
"""
import matplotlib.pyplot as plt
from mplsoccer import Pitch

from visuals.chart_utils import (
    BG_DARK, BG_PANEL, LINE_COLOR, fig_to_b64, layout_pitch_axes, draw_title,
    generate_stat_bar_chart, percentile_color,
)

SAVED_COLOR = "#3b82f6"
CONCEDED_COLOR = "#ef4444"


def generate_goalkeeping_chart(player_name: str, team: str, season: str, shots: list[dict]) -> str:
    pitch = Pitch(pitch_type="opta", pitch_color=BG_PANEL, line_color=LINE_COLOR, linewidth=1.2, half=False)
    fig, ax = pitch.draw(figsize=(11, 7.3))
    fig.set_facecolor(BG_DARK)
    layout_pitch_axes(ax, top=0.80, bottom=0.11)

    saved_n = conceded_n = 0
    for s in shots:
        if s["x"] is None or s["y"] is None:
            continue
        if s["outcome"] == "saved":
            saved_n += 1
            pitch.scatter(s["x"], s["y"], ax=ax, color=SAVED_COLOR, s=60, zorder=4,
                          edgecolors="white", linewidth=0.4)
        else:
            conceded_n += 1
            pitch.scatter(s["x"], s["y"], ax=ax, color=CONCEDED_COLOR, s=95, marker="*", zorder=5,
                          edgecolors="white", linewidth=0.5)

    n = saved_n + conceded_n
    save_pct = round(100 * saved_n / n) if n else 0
    subtitle = f"Shots Faced | {team} | {season}    Shots faced: {n}    Save rate: {save_pct}%"
    draw_title(fig, player_name, subtitle)

    handles = [
        plt.Line2D([0], [0], marker="o", color="none", markerfacecolor=SAVED_COLOR, markersize=9, markeredgecolor="white"),
        plt.Line2D([0], [0], marker="*", color="none", markerfacecolor=CONCEDED_COLOR, markersize=13, markeredgecolor="white"),
    ]
    fig.legend(handles, [f"Saved: {saved_n}", f"Conceded: {conceded_n}"], loc="lower center", ncol=2,
               frameon=False, labelcolor="#cbd5e1", fontsize=8.5, bbox_to_anchor=(0.5, 0.02))
    return fig_to_b64(fig)


def generate_gk_outcome_chart(player_name: str, team: str, season: str, shots: list[dict]) -> str:
    """Saved vs conceded share of every shot faced."""
    n = len(shots)
    saved_n = sum(1 for s in shots if s["outcome"] == "saved")
    conceded_n = n - saved_n
    items = [
        ("Saved", 100 * saved_n / n if n else 0, SAVED_COLOR, f"{saved_n} ({round(100*saved_n/n) if n else 0}%)"),
        ("Conceded", 100 * conceded_n / n if n else 0, CONCEDED_COLOR, f"{conceded_n} ({round(100*conceded_n/n) if n else 0}%)"),
    ]
    return generate_stat_bar_chart("Shots Faced Outcome", f"{team} | {season}    Faced: {n}", items)


def generate_gk_distribution_chart(player_name: str, team: str, season: str, stats: list[dict]) -> str:
    """Distribution profile — accuracy and how often the keeper plays it
    short vs long — pulled from the stat card's own percentiles."""
    by_label = {s["label"]: s for s in stats}
    labels = ("Distribution accuracy", "Plays short", "Save rate")
    items = []
    for label in labels:
        s = by_label.get(label)
        if not s or s.get("no_data"):
            items.append((label, 0, "#374151", "—"))
            continue
        pct = s["percentile"]
        items.append((label, pct, percentile_color(pct), f"{s['value']}{s.get('unit','')}"))
    return generate_stat_bar_chart("Distribution Profile", f"{team} | {season}", items)
