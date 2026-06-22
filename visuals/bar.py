"""
Grouped horizontal bar chart — supports 1–4 players.
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


def generate_bar(norms: list, names: list, custom_colors: list = None, cfg: dict = None) -> str:
    color_palette = (list(custom_colors) + COLORS)[:len(norms)] if custom_colors else COLORS

    config   = cfg if cfg is not None else get_position_config(norms[0].get("position", "Attacker"))
    labels   = config["labels"]
    metrics  = config["metrics"]
    max_vals = config["max_vals"]

    n_players = len(norms)
    n_metrics = len(labels)
    x         = np.arange(n_metrics)
    total_w   = 0.7
    bar_w     = total_w / n_players
    offsets   = np.linspace(-total_w/2 + bar_w/2, total_w/2 - bar_w/2, n_players)

    # Uniform 8x8 figure to fill the card container
    fig, ax = plt.subplots(figsize=(8, 8), facecolor=BG_DARK)
    ax.set_facecolor(BG_PANEL)

    for i, (norm, name, color, offset) in enumerate(zip(norms, names, color_palette, offsets)):
        vals = [norm.get(m, 0) or 0 for m in metrics]
        bars = ax.bar(x + offset, vals, bar_w, label=name,
                      color=color, alpha=0.88, zorder=3,
                      edgecolor="none", linewidth=0)
        for rect in bars:
            h = rect.get_height()
            if h > 0:
                ax.annotate(f"{h:.2f}",
                            xy=(rect.get_x() + rect.get_width() / 2, h),
                            xytext=(0, 3), textcoords="offset points",
                            ha="center", va="bottom",
                            color=color, fontsize=7.5, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(labels, color="#e2e8f0", fontsize=9.5, rotation=20, ha="right")
    ax.tick_params(axis="y", colors="#6b7280")
    ax.set_ylabel("Value (Per 90 mins)", color="#6b7280", fontsize=9)
    # Compact internal legend to save vertical space
    legend = ax.legend(facecolor="#1a2235", edgecolor=GRID_COL, fontsize=9.5, 
                       loc="upper right", bbox_to_anchor=(0.98, 0.98))
    for txt in legend.get_texts():
        txt.set_color("white")

    ax.grid(axis="y", color=GRID_COL, linewidth=0.8, alpha=0.6, zorder=0)
    for spine in ["bottom", "left"]:
        ax.spines[spine].set_color(GRID_COL)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.tight_layout(pad=2.0)
    return _fig_to_b64(fig)
