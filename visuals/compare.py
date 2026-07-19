"""
Compare page — an overlaid radar of a small fixed set of headline
cross-category metrics (one axis per metric, one polygon per player), for a
fast eyeball read before diving into the full per-tab stat tables. Values are
each player's own percentile (already computed by build_all_categories
against THEIR OWN position cohort) — comparing percentiles rather than raw
units is what makes putting a full-back and a striker on the same axes
meaningful at all.
"""
import math

import matplotlib.pyplot as plt

from core.advanced.composite import category_percentile
from core.advanced.metrics_master import CATEGORY_ORDER
from visuals.chart_utils import BG_DARK, BG_PANEL, fig_to_b64, generate_stat_bar_chart

CATEGORY_LABELS_SHORT = {
    "passing": "Passing", "shooting": "Shooting", "carrying": "Carrying",
    "half_spaces": "Half-Spaces", "tempo": "Tempo", "decision_making": "Decisions",
    "final_third": "Final Third", "aerial": "Aerial", "defending": "Defending",
    "holdup": "Hold-Up", "post_recovery": "Post-Recovery", "goalkeeping": "Goalkeeping",
}

# (category key, stat label) pairs — one axis per entry. A player missing
# that category (e.g. a keeper viewing "Aerial Duels", which is hidden for
# GKs — see percentiles.GK_VISIBLE_OUTFIELD_CATEGORIES) just plots 0 on that
# axis rather than erroring, since there's nothing meaningful to show anyway.
RADAR_METRICS = [
    ("passing", "Progressive passes"),
    ("carrying", "Progressive carries"),
    ("shooting", "Goals"),
    ("aerial", "Aerial duels"),
    ("defending", "Tackles"),
    ("final_third", "Completeness"),
]
RADAR_LABELS = ["Prog. Passes", "Prog. Carries", "Goals", "Aerial Duels", "Tackles", "Final Third"]

PLAYER_COLORS = ["#3b82f6", "#f43f5e", "#10b981", "#f59e0b"]


def _percentile_for(cats: list[dict], cat_key: str, label: str) -> float:
    cat = next((c for c in cats if c["key"] == cat_key), None)
    if not cat:
        return 0.0
    stats = cat["rows"][0]["stats"] if cat.get("rows") else []
    s = next((s for s in stats if s["label"] == label), None)
    if not s or s.get("no_data"):
        return 0.0
    return float(s["percentile"])


def generate_comparison_radar(players: list[dict]) -> str:
    """players: [{"name": str, "cats": <build_all_categories() output>}, ...] (2-4 entries)."""
    n_axes = len(RADAR_METRICS)
    angles = [2 * math.pi * i / n_axes for i in range(n_axes)]
    angles += angles[:1]

    fig = plt.figure(figsize=(7.2, 7.2))
    fig.set_facecolor(BG_DARK)
    ax = fig.add_subplot(111, projection="polar")
    ax.set_facecolor(BG_DARK)
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)

    for i, p in enumerate(players):
        color = PLAYER_COLORS[i % len(PLAYER_COLORS)]
        values = [_percentile_for(p["cats"], cat_key, label) for cat_key, label in RADAR_METRICS]
        values += values[:1]
        ax.plot(angles, values, color=color, linewidth=2, zorder=3, label=p["name"])
        ax.fill(angles, values, color=color, alpha=0.15, zorder=2)

    ax.set_ylim(0, 100)
    ax.set_yticks([25, 50, 75, 100])
    ax.set_yticklabels(["25", "50", "75", "100"], color="#64748b", fontsize=8)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(RADAR_LABELS, color="#cbd5e1", fontsize=10.5)
    ax.grid(color="#374151", alpha=0.5)
    ax.spines["polar"].set_color("#374151")

    fig.suptitle("Headline Comparison", color="white", fontsize=16, fontweight="bold", y=0.98)
    fig.legend(loc="lower center", ncol=min(len(players), 4), frameon=False,
               labelcolor="#cbd5e1", fontsize=9.5, bbox_to_anchor=(0.5, -0.02))
    plt.tight_layout(rect=[0.02, 0.05, 0.98, 0.94])
    return fig_to_b64(fig)


def generate_composite_bar_chart(players: list[dict]) -> str:
    """players: [{"name": str, "composite": {"score": float|None}}, ...] —
    the position-weighted rating (core.advanced.composite) as a simple
    ranked bar, one per player."""
    items = []
    for i, p in enumerate(players):
        score = p["composite"]["score"]
        color = PLAYER_COLORS[i % len(PLAYER_COLORS)]
        items.append((p["name"], score if score is not None else 0, color, f"{score}" if score is not None else "—"))
    return generate_stat_bar_chart("Composite Rating", "Position-weighted across every category", items)


def generate_category_comparison_chart(players: list[dict]) -> str:
    """Grouped bar: one cluster per Advanced Metrics category (mean percentile
    across that category's stats), one colored bar per player per cluster —
    the full-width, all-12-category companion to the fixed 6-metric radar."""
    cats_present = [key for key in CATEGORY_ORDER if key != "linkup"
                    and any(any(c["key"] == key for c in p["cats"]) for p in players)]
    if not cats_present:
        cats_present = ["passing"]

    n_players = len(players)
    x = list(range(len(cats_present)))
    width = 0.8 / n_players

    fig, ax = plt.subplots(figsize=(11.5, 5.6))
    fig.set_facecolor(BG_DARK)
    ax.set_facecolor(BG_PANEL)

    for i, p in enumerate(players):
        vals = []
        for key in cats_present:
            cat = next((c for c in p["cats"] if c["key"] == key), None)
            pct = category_percentile(cat) if cat else None
            vals.append(pct if pct is not None else 0)
        offsets = [xi + (i - (n_players - 1) / 2) * width for xi in x]
        ax.bar(offsets, vals, width=width * 0.9, color=PLAYER_COLORS[i % len(PLAYER_COLORS)],
               label=p["name"], zorder=3)

    ax.set_xticks(x)
    ax.set_xticklabels([CATEGORY_LABELS_SHORT.get(k, k) for k in cats_present], rotation=30, ha="right",
                        color="#cbd5e1", fontsize=9.5)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Category percentile", color="#94a3b8", fontsize=9.5)
    ax.tick_params(colors="#94a3b8", labelsize=9)
    for spine in ax.spines.values():
        spine.set_color("#374151")
    ax.grid(axis="y", color="#374151", alpha=0.3, zorder=0)
    ax.legend(loc="upper right", frameon=False, labelcolor="#cbd5e1", fontsize=9.5)

    fig.suptitle("Category Percentile Comparison", color="white", fontsize=15.5, fontweight="bold", y=0.975)
    plt.tight_layout(rect=[0.02, 0.02, 0.98, 0.90])
    return fig_to_b64(fig)
