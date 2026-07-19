"""
Post-Recovery — what a player does in the action immediately after winning
the ball back. Same reception/outcome shape as Combination Play, so it
reuses that visual language (recovery point -> what came next).
"""
import matplotlib.pyplot as plt
from mplsoccer import Pitch

from core.advanced.geometry import zone_third
from visuals.chart_utils import BG_DARK, BG_PANEL, LINE_COLOR, fig_to_b64, layout_pitch_axes, draw_title, generate_stat_bar_chart

OUTCOME_STYLE = {
    "prog_pass":    {"color": "#22c55e", "label": "Prog. Passes"},
    "pass":         {"color": "#3b82f6", "label": "Passes"},
    "prog_carry":   {"color": "#ef4444", "label": "Prog. Carries", "dashed": True},
    "unsuccessful": {"color": "#6b7280", "label": "Unsuccessful"},
}
RECOVERY_COLOR = "#eab308"


def generate_post_recovery_chart(player_name: str, team: str, season: str, recoveries: list[dict]) -> str:
    pitch = Pitch(pitch_type="opta", pitch_color=BG_PANEL, line_color=LINE_COLOR, linewidth=1.2, half=False)
    fig, ax = pitch.draw(figsize=(11, 7.3))
    fig.set_facecolor(BG_DARK)
    layout_pitch_axes(ax, top=0.80, bottom=0.12)

    counts = {k: 0 for k in OUTCOME_STYLE}
    for r in recoveries:
        if r["x"] is None or r["y"] is None:
            continue
        outcome = r["outcome"]
        counts[outcome] = counts.get(outcome, 0) + 1
        pitch.scatter(r["x"], r["y"], ax=ax, color=RECOVERY_COLOR, s=14, alpha=0.6, zorder=2)
        style = OUTCOME_STYLE.get(outcome)
        if style and r["end_x"] is not None and r["end_y"] is not None:
            pitch.lines(r["x"], r["y"], r["end_x"], r["end_y"], ax=ax, color=style["color"], lw=1.5,
                        linestyle="--" if style.get("dashed") else "-", alpha=0.8, zorder=3)

    n = len(recoveries)
    ret_pct = round(100 * (n - counts.get("unsuccessful", 0)) / n) if n else 0
    subtitle = f"Post-Recovery Sequences | {team} | {season}    Recoveries: {n}    Retention: {ret_pct}%"
    draw_title(fig, player_name, subtitle)

    handles = [plt.Line2D([0], [0], marker="o", color="none", markerfacecolor=RECOVERY_COLOR, markersize=6, markeredgecolor="none")]
    labels = [f"Recoveries: {n}"]
    for k, v in OUTCOME_STYLE.items():
        handles.append(plt.Line2D([0], [0], color=v["color"], lw=2.2, linestyle="--" if v.get("dashed") else "-"))
        labels.append(f"{v['label']}: {counts[k]}")
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False,
               labelcolor="#cbd5e1", fontsize=8, bbox_to_anchor=(0.5, 0.02))
    return fig_to_b64(fig)


def generate_post_recovery_outcome_chart(player_name: str, team: str, season: str, recoveries: list[dict]) -> str:
    """What this player does immediately after winning the ball back — share
    across the same outcome buckets as the map's own legend."""
    n = len(recoveries)
    counts = {k: 0 for k in OUTCOME_STYLE}
    for r in recoveries:
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
    items = [(v["label"], 100 * counts[k] / n if n else 0, v["color"], f"{counts[k]} ({round(100*counts[k]/n) if n else 0}%)")
              for k, v in OUTCOME_STYLE.items()]
    return generate_stat_bar_chart("Post-Recovery Outcome Breakdown", f"{team} | {season}    Recoveries: {n}", items)


THIRD_COLORS = {"def": "#3b82f6", "mid": "#eab308", "att": "#22c55e"}
THIRD_LABELS = {"def": "Defensive Third", "mid": "Middle Third", "att": "Attacking Third"}


def generate_post_recovery_zone_chart(player_name: str, team: str, season: str, recoveries: list[dict]) -> str:
    """Where on the pitch this player wins the ball back — a winger pressing
    high recovers in the attacking third far more than a deep-lying CB."""
    counts = {"def": 0, "mid": 0, "att": 0}
    for r in recoveries:
        if r["x"] is None:
            continue
        counts[zone_third(r["x"])] += 1
    n = sum(counts.values())
    items = [(THIRD_LABELS[z], 100 * counts[z] / n if n else 0, THIRD_COLORS[z], f"{counts[z]} ({round(100*counts[z]/n) if n else 0}%)")
              for z in ("def", "mid", "att")]
    return generate_stat_bar_chart("Recoveries by Third", f"{team} | {season}    Total: {n}", items)
