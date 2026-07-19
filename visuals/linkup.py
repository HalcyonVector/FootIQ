"""
Combination Play pitch chart: for a chosen passer -> receiver pair, plots
every reception (yellow) and what the receiver did next, colored by
outcome. Uses mplsoccer's Pitch with pitch_type='opta' since that's exactly
the 0-100 coordinate system our event data already uses — no conversion needed.
"""
import matplotlib.pyplot as plt
from mplsoccer import Pitch

from visuals.chart_utils import BG_DARK, BG_PANEL, LINE_COLOR, fig_to_b64, layout_pitch_axes, draw_title

OUTCOME_STYLE = {
    "prog_pass":   {"color": "#22c55e", "label": "Prog. Passes"},
    "pass":        {"color": "#3b82f6", "label": "Passes"},
    "unsuccessful": {"color": "#6b7280", "label": "Unsuccessful"},
    "prog_carry":  {"color": "#ef4444", "label": "Prog. Carries", "dashed": True},
}
TAKEON_WON_COLOR = "#3b82f6"
TAKEON_LOST_COLOR = "#9ca3af"
SHOT_COLOR = "#ec4899"
RECEPTION_COLOR = "#eab308"


def generate_linkup_chart(passer_name: str, receiver_name: str, receptions: list[dict]) -> str:
    pitch = Pitch(pitch_type="opta", pitch_color=BG_PANEL, line_color=LINE_COLOR,
                  linewidth=1.2, half=False)
    fig, ax = pitch.draw(figsize=(11, 7.3))
    fig.set_facecolor(BG_DARK)
    layout_pitch_axes(ax, top=0.80, bottom=0.12)

    counts = {"prog_pass": 0, "pass": 0, "unsuccessful": 0, "prog_carry": 0,
              "takeon_won": 0, "takeon_lost": 0, "shot": 0}

    for r in receptions:
        rx, ry = r["reception_x"], r["reception_y"]
        ex, ey = r.get("end_x"), r.get("end_y")
        outcome = r["outcome"]
        counts[outcome] = counts.get(outcome, 0) + 1

        if outcome in OUTCOME_STYLE and ex is not None and ey is not None:
            style = OUTCOME_STYLE[outcome]
            pitch.lines(rx, ry, ex, ey, ax=ax, color=style["color"], lw=1.6,
                        linestyle="--" if style.get("dashed") else "-", alpha=0.85, zorder=3)
        elif outcome == "takeon_won":
            pitch.scatter(rx, ry, ax=ax, color=TAKEON_WON_COLOR, s=45, zorder=4, edgecolors="white", linewidth=0.4)
        elif outcome == "takeon_lost":
            pitch.scatter(rx, ry, ax=ax, color=TAKEON_LOST_COLOR, s=45, zorder=4, edgecolors="white", linewidth=0.4)
        elif outcome == "shot":
            pitch.scatter(rx, ry, ax=ax, color=SHOT_COLOR, s=90, marker="p", zorder=5, edgecolors="white", linewidth=0.5)

        pitch.scatter(rx, ry, ax=ax, color=RECEPTION_COLOR, s=14, alpha=0.6, zorder=2)

    n = len(receptions)
    prog_pct = round(100 * (counts["prog_pass"] + counts["prog_carry"]) / n) if n else 0
    draw_title(fig, receiver_name,
               f"After receiving from {passer_name} | {n} receptions | progresses {prog_pct}%")

    legend_items = [
        (RECEPTION_COLOR, f"Pass from {passer_name}"),
        (OUTCOME_STYLE["prog_pass"]["color"], f"Prog. Passes: {counts['prog_pass']}"),
        (OUTCOME_STYLE["pass"]["color"], f"Passes: {counts['pass']}"),
        (OUTCOME_STYLE["unsuccessful"]["color"], f"Unsuccessful: {counts['unsuccessful']}"),
        (OUTCOME_STYLE["prog_carry"]["color"], f"Prog. Carries: {counts['prog_carry']}"),
        (TAKEON_WON_COLOR, f"Take-Ons won: {counts['takeon_won']}"),
        (TAKEON_LOST_COLOR, f"Take-Ons lost: {counts['takeon_lost']}"),
        (SHOT_COLOR, f"Shots: {counts['shot']}"),
    ]
    handles = [plt.Line2D([0], [0], color=c, lw=2.5, marker="o", markersize=5) for c, _ in legend_items]
    labels = [lbl for _, lbl in legend_items]
    fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False,
               labelcolor="#cbd5e1", fontsize=8.5, bbox_to_anchor=(0.5, 0.02))

    return fig_to_b64(fig)
