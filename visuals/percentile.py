"""
Horizontal percentile chart — N players, N track rows per metric.
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


def generate_percentile(norms: list, names: list, custom_colors: list = None, cfg: dict = None) -> str:
    color_palette = (list(custom_colors) + COLORS)[:len(norms)] if custom_colors else COLORS

    config   = cfg if cfg is not None else get_position_config(norms[0].get("position", "Attacker"))
    labels   = config["labels"]
    metrics  = config["metrics"]
    max_vals = config["max_vals"]

    n_players = len(norms)
    n_metrics = len(labels)
    bar_h     = 0.7 / n_players
    group_gap = 0.3

    # Y positions: one group per metric, spaced to avoid overlap
    group_centers = np.arange(n_metrics) * (1 + group_gap)
    offsets       = np.linspace(-0.35 + bar_h/2, 0.35 - bar_h/2, n_players)

    # Tighter spacing for benchmark comparison
    fig_h = max(8, n_metrics * 0.9)
    fig, ax = plt.subplots(figsize=(8, fig_h), facecolor=BG_DARK)
    ax.set_facecolor(BG_PANEL)

    for i, (norm, name, color, offset) in enumerate(zip(norms, names, color_palette, offsets)):
        pcts = [min((norm.get(m, 0) or 0) / mv, 1.0) * 100 if mv > 0 else 0
                for m, mv in zip(metrics, max_vals)]
        y_pos = group_centers + offset

        # Track bars (background)
        ax.barh(y_pos, [100] * n_metrics, bar_h, color="#1e2535", zorder=1, left=0)
        # Value bars
        bars = ax.barh(y_pos, pcts, bar_h, label=name,
                       color=color, alpha=0.87, zorder=3)

        for bar, pct in zip(bars, pcts):
            label_x = pct - 2 if pct > 15 else pct + 1
            ha = "right" if pct > 15 else "left"
            ax.text(label_x, bar.get_y() + bar.get_height() / 2,
                    f"{pct:.0f}%", va="center", ha=ha,
                    color="white" if pct > 15 else color, fontsize=7.5, fontweight="bold")

    ax.axvline(50, color="#4b5563", linewidth=1.2, linestyle="--", zorder=2)
    ax.set_yticks(group_centers)
    ax.set_yticklabels(labels, color="#e2e8f0", fontsize=10)
    ax.set_xlim(0, 100)
    ax.set_xlabel("% of benchmark max", color="#6b7280", fontsize=9)
    ax.set_title("Benchmark Percentile Chart", color="white",
                 fontsize=13, fontweight="bold", pad=14)

    for spine in ax.spines.values():
        spine.set_color(GRID_COL)
    ax.tick_params(colors="#6b7280")

    # Compact internal legend
    legend = ax.legend(facecolor="#1a2235", edgecolor=GRID_COL,
                       fontsize=9.5, loc="lower right", bbox_to_anchor=(0.98, 0.02))
    for txt in legend.get_texts():
        txt.set_color("white")

    plt.tight_layout(pad=1.5)
    return _fig_to_b64(fig)
