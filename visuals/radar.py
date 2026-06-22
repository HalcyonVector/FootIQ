"""
Radar chart — supports 1–4 players, all using the first player's position config.
Returns a base64 PNG string.
"""
import io, base64
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from core.scorer import get_position_config

BG_DARK   = "#0a0e1a"
BG_PANEL  = "#111827"
GRID_COL  = "#1f2937"
COLORS    = ["#3b82f6", "#f43f5e", "#10b981", "#f59e0b"]


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight",
                facecolor=fig.get_facecolor(), dpi=110)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return encoded


def generate_radar(norms: list, names: list, custom_colors: list = None, cfg: dict = None) -> str:
    color_palette = (list(custom_colors) + COLORS)[:len(norms)] if custom_colors else COLORS

    config   = cfg if cfg is not None else get_position_config(norms[0].get("position", "Attacker"))
    labels   = config["labels"]
    metrics  = config["metrics"]
    max_vals = config["max_vals"]

    N      = len(labels)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()

    # Uniform 8x8 figure with expansion
    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={"polar": True}, facecolor=BG_DARK)
    ax.set_facecolor(BG_PANEL)

    for norm, name, color in zip(norms, names, color_palette):
        vals = [min((norm.get(m, 0) or 0) / mv, 1.0) if mv > 0 else 0.0
                for m, mv in zip(metrics, max_vals)]
        v_plot = vals + [vals[0]]
        a_plot = angles + [angles[0]]

        ax.fill(a_plot, v_plot, color=color, alpha=0.14)
        ax.plot(a_plot, v_plot, color=color, linewidth=2.2, label=name)
        ax.scatter(angles, vals, color=color, s=65, zorder=5)

    ax.set_xticks(angles)
    ax.set_xticklabels(labels, color="#e2e8f0", fontsize=9.5, fontweight="bold")
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["25%", "50%", "75%", "100%"], color="#4b5563", fontsize=7)
    ax.yaxis.set_tick_params(labelcolor="#4b5563")
    ax.grid(color=GRID_COL, linewidth=0.8)
    ax.spines["polar"].set_color(GRID_COL)

    # Compressed internal legend
    legend = ax.legend(loc="upper right", bbox_to_anchor=(1.15, 1.1),
                       facecolor=BG_PANEL, edgecolor=GRID_COL, framealpha=0.6, fontsize=9.5)
    for txt in legend.get_texts():
        txt.set_color("white")

    fig.suptitle("Radar Comparison", color="white", fontsize=13,
                 fontweight="bold", y=1.02)
    return _fig_to_b64(fig)
