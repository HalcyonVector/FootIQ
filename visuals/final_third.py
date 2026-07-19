"""
Final Third — scatter of Completeness (floor, x-axis) vs Impact (ceiling,
y-axis) across the player's position cohort, with the target player
highlighted and the four quadrants labeled.
"""
import matplotlib.pyplot as plt

from visuals.chart_utils import BG_DARK, BG_PANEL, fig_to_b64, generate_stat_bar_chart, generate_histogram_chart, percentile_color

DOT_COLOR = "#475569"
TARGET_COLOR = "#8b5cf6"


def generate_final_third_scatter(player_name: str, team: str, season: str, points: list[dict]) -> str:
    fig, ax = plt.subplots(figsize=(8.6, 7.4))
    fig.set_facecolor(BG_DARK)
    ax.set_facecolor(BG_PANEL)

    xs = [p["completeness"] for p in points if not p["is_target"]]
    ys = [p["impact"] for p in points if not p["is_target"]]
    ax.scatter(xs, ys, color=DOT_COLOR, s=26, alpha=0.55, zorder=2, edgecolors="none")

    target = next((p for p in points if p["is_target"]), None)
    if target:
        ax.scatter([target["completeness"]], [target["impact"]], color=TARGET_COLOR, s=170, zorder=4,
                   edgecolors="white", linewidth=1.6)
        ax.annotate(player_name, (target["completeness"], target["impact"]), color="white", fontsize=10,
                    fontweight="bold", xytext=(10, 10), textcoords="offset points", zorder=5)

    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axhline(50, color="#374151", linewidth=1, zorder=1)
    ax.axvline(50, color="#374151", linewidth=1, zorder=1)
    for spine in ax.spines.values():
        spine.set_color("#374151")
    ax.tick_params(colors="#94a3b8", labelsize=9)
    ax.set_xlabel("Completeness (floor — sustained all-round involvement)", color="#94a3b8", fontsize=9.5)
    ax.set_ylabel("Impact (ceiling — damage per touch)", color="#94a3b8", fontsize=9.5)

    quad_style = dict(color="#64748b", fontsize=9, fontweight="700", alpha=0.85)
    ax.text(3, 97, "MOMENTS PLAYER", va="top", ha="left", **quad_style)
    ax.text(97, 97, "COMPLETE & DECISIVE", va="top", ha="right", **quad_style)
    ax.text(3, 3, "PERIPHERAL", va="bottom", ha="left", **quad_style)
    ax.text(97, 3, "CONNECTOR", va="bottom", ha="right", **quad_style)

    fig.suptitle(player_name, color="white", fontsize=17, fontweight="bold", y=0.98, verticalalignment="top")
    fig.text(0.5, 0.90, f"Final Third: Completeness vs Impact | {team} | {season}", color="#94a3b8", fontsize=10, ha="center", va="top")
    plt.tight_layout(rect=[0.02, 0.02, 0.98, 0.88])
    return fig_to_b64(fig)


PILLAR_LABELS = {"shooting": "Shooting", "linkup": "Link-Up", "carrying": "Carrying", "ballwinning": "Ball Winning"}
PILLAR_COLORS = {"shooting": "#eab308", "linkup": "#3b82f6", "carrying": "#ef4444", "ballwinning": "#22c55e"}


def generate_pillar_bar_chart(player_name: str, team: str, season: str, floor_pct: dict, per_touch_pct: dict) -> str:
    """The 4 pillars' floor (volume) vs per-touch (efficiency) percentiles,
    side by side — Completeness/Impact are composites of exactly these 8
    numbers, so this is what's actually driving those two headline scores."""
    items = []
    for p in ("shooting", "linkup", "carrying", "ballwinning"):
        items.append((f"{PILLAR_LABELS[p]} (floor)", floor_pct[p], PILLAR_COLORS[p], f"{floor_pct[p]}th pct"))
    for p in ("shooting", "linkup", "carrying", "ballwinning"):
        items.append((f"{PILLAR_LABELS[p]} (per touch)", per_touch_pct[p], PILLAR_COLORS[p], f"{per_touch_pct[p]}th pct"))
    return generate_stat_bar_chart("Four Pillars — Floor vs Per-Touch", f"{team} | {season}", items)


def generate_completeness_distribution_chart(player_name: str, team: str, season: str,
                                              cohort_points: list[dict], player_completeness: float) -> str:
    """Where this player's Completeness score sits in their position cohort's
    distribution — Completeness alone doesn't say whether 55 is middling or
    actually quite good for a winger."""
    values = [p["completeness"] for p in cohort_points if p.get("completeness") is not None]
    marker = (player_completeness, f"{player_name}: {player_completeness}") if player_completeness is not None else None
    return generate_histogram_chart("Completeness — Cohort Distribution", f"{team} | {season}    Cohort size: {len(values)}",
                                     values, bins=14, unit="", color="#475569", marker=marker)
