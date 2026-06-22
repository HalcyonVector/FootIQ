"""
Lollipop chart — clean alternative to bar chart for N players.
Shows each stat as a dot-on-stem; great for seeing deltas at a glance.
Returns a base64 PNG string.
"""
import io, base64
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from core.scorer import get_position_config

BG_DARK  = "#0a0e1a"
BG_PANEL = "#111827"
GRID_COL = "#1f2937"
COLORS   = ["#3b82f6", "#f43f5e", "#10b981", "#f59e0b"]


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight",
                facecolor=fig.get_facecolor(), dpi=110)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return encoded


def generate_lollipop(norms: list, names: list, custom_colors: list = None, cfg: dict = None) -> str:
    color_palette = (list(custom_colors) + COLORS)[:len(norms)] if custom_colors else COLORS

    config   = cfg if cfg is not None else get_position_config(norms[0].get("position", "Attacker"))
    labels   = config["labels"]
    metrics  = config["metrics"]
    max_vals = config["max_vals"]

    n_players = len(norms)
    n_metrics = len(labels)
    x         = np.arange(n_metrics)
    spread    = 0.25
    offsets   = np.linspace(-spread * (n_players-1)/2,
                             spread * (n_players-1)/2, n_players)

    # Uniform 8x8 figure to fill the card container
    fig, ax = plt.subplots(figsize=(8, 8), facecolor=BG_DARK)
    ax.set_facecolor(BG_PANEL)

    for norm, name, color, offset in zip(norms, names, color_palette, offsets):
        pcts = [min((norm.get(m, 0) or 0) / mv, 1.0) * 100 if mv > 0 else 0
                for m, mv in zip(metrics, max_vals)]
        xp = x + offset
        # Stems
        for xi, pct in zip(xp, pcts):
            ax.vlines(xi, 0, pct, color=color, linewidth=2.0, alpha=0.55, zorder=2)
        # Dots
        ax.scatter(xp, pcts, color=color, s=110, zorder=5,
                   label=name, edgecolors="white", linewidths=0.5)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, color="#e2e8f0", fontsize=9.5, rotation=20, ha="right")
    ax.set_ylim(0, 105)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"], color="#6b7280", fontsize=8)
    ax.axhline(50, color="#374151", linewidth=1.0, linestyle="--", zorder=1, alpha=0.8)
    ax.set_ylabel("% of Benchmark Max", color="#6b7280", fontsize=9)
    # Compact internal legend to save vertical space
    legend = ax.legend(facecolor="#1a2235", edgecolor=GRID_COL,
                       fontsize=9.5, loc="upper right", bbox_to_anchor=(0.98, 0.98))
    for txt in legend.get_texts():
        txt.set_color("white")

    ax.grid(axis="y", color=GRID_COL, linewidth=0.8, alpha=0.5, zorder=0)
    for spine in ["bottom", "left"]:
        ax.spines[spine].set_color(GRID_COL)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.tight_layout(pad=2.0)
    return _fig_to_b64(fig)
