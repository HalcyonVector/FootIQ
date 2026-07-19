"""
Decision Making "bloom" — a radial bar per sub-metric, length/color = that
metric's percentile within the cohort (same numbers already shown in the
stat card, just visualized). No raw event data needed.
"""
import math

import matplotlib.pyplot as plt

from visuals.chart_utils import BG_DARK, fig_to_b64, percentile_color, generate_stat_bar_chart


def generate_decision_bloom_chart(player_name: str, team: str, season: str, stats: list[dict]) -> str:
    labels = [s["label"] for s in stats]
    values = [max(2, s["percentile"]) for s in stats]
    n = len(labels)

    fig = plt.figure(figsize=(6.6, 6.6))
    fig.set_facecolor(BG_DARK)
    ax = fig.add_subplot(111, projection="polar")
    ax.set_facecolor(BG_DARK)
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)

    angles = [2 * math.pi * i / n for i in range(n)] if n else []
    width = (2 * math.pi / n * 0.78) if n else 0
    colors = [percentile_color(v) for v in values]

    if n:
        ax.bar(angles, values, width=width, bottom=0, color=colors, alpha=0.9,
               edgecolor=BG_DARK, linewidth=2, zorder=3)
        for angle, val, lbl in zip(angles, values, labels):
            ax.text(angle, 112, lbl.upper(), ha="center", va="center", color="#94a3b8", fontsize=7.6, zorder=4)
            ax.text(angle, val + 8 if val < 95 else val - 10, str(int(val)), ha="center", va="center",
                    color="white", fontsize=9.5, fontweight="bold", zorder=5)

    ax.set_ylim(0, 122)
    ax.set_yticklabels([])
    ax.set_xticklabels([])
    ax.grid(color="#374151", alpha=0.25)
    ax.spines["polar"].set_visible(False)

    overall = round(sum(values) / n) if n else 0
    ax.text(0, -30, f"{overall}", ha="center", va="center", color="white", fontsize=22, fontweight="bold", zorder=6)
    ax.text(0, -55, "DECISION", ha="center", va="center", color="#64748b", fontsize=9, fontweight="bold", zorder=6)

    fig.suptitle(f"{player_name}", color="white", fontsize=17, fontweight="bold", y=0.985, verticalalignment="top")
    fig.text(0.5, 0.895, f"Decision-Making Bloom | {team} | {season}", color="#94a3b8", fontsize=10, ha="center", va="top")
    return fig_to_b64(fig)


def generate_decision_bar_chart(player_name: str, team: str, season: str, stats: list[dict]) -> str:
    """The same percentiles as the bloom chart, as a plain ranked bar list —
    easier to read off exact standings than the radial version at a glance."""
    ordered = sorted(stats, key=lambda s: s["percentile"], reverse=True)
    items = [(s["label"], s["percentile"], percentile_color(s["percentile"]), f"{s['percentile']}th pct") for s in ordered]
    return generate_stat_bar_chart("Decision-Making Percentiles", f"{team} | {season}", items)
