"""
FBRef-style pizza / polar bar chart for a single player.
Each slice = one stat, filled to the player's percentile of benchmark max.
Returns a base64 PNG string.
"""
import io, base64
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import numpy as np

from core.scorer import get_position_config

BG_DARK  = "#0a0e1a"
BG_PANEL = "#111827"


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight",
                facecolor=fig.get_facecolor(), dpi=110)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return encoded


def _pct_color(pct: float) -> str:
    """Map 0–1 percentile → color (dark red → amber → bright blue)."""
    stops = [
        (0.00, (239, 68,  68)),   # red
        (0.25, (249, 115, 22)),   # orange
        (0.50, (234, 179,  8)),   # yellow
        (0.75, ( 34, 197, 94)),   # green
        (1.00, ( 59, 130,246)),   # blue
    ]
    pct = max(0.0, min(1.0, pct))
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        if t0 <= pct <= t1:
            alpha = (pct - t0) / (t1 - t0)
            r = int(c0[0] + alpha * (c1[0] - c0[0]))
            g = int(c0[1] + alpha * (c1[1] - c0[1]))
            b = int(c0[2] + alpha * (c1[2] - c0[2]))
            return f"#{r:02x}{g:02x}{b:02x}"
    return "#3b82f6"


def generate_pizza(norm: dict, name: str, color_override: str = None) -> str:
    config   = get_position_config(norm.get("position", "Attacker"))
    labels   = config["labels"]
    metrics  = config["metrics"]
    max_vals = config["max_vals"]

    pcts = [min((norm.get(m, 0) or 0) / mv, 1.0) if mv > 0 else 0.0
            for m, mv in zip(metrics, max_vals)]

    N      = len(labels)
    angles = np.linspace(np.pi / 2, np.pi / 2 + 2 * np.pi, N, endpoint=False)
    width  = 2 * np.pi / N * 0.82

    # Uniform 8x8 figure for professional scaling
    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={"projection": "polar"},
                           facecolor=BG_DARK)
    ax.set_facecolor(BG_PANEL)

    INNER = 0.15   # blank hub radius
    OUTER = 1.00   # max bar reaches here

    for angle, pct, label in zip(angles, pcts, labels):
        bar_height = INNER + pct * (OUTER - INNER)
        color = color_override if color_override else _pct_color(pct)

        # Background track
        ax.bar(angle, OUTER - INNER, width=width, bottom=INNER,
               color="#1e2535", alpha=1.0, zorder=1)
        # Value bar
        ax.bar(angle, bar_height - INNER, width=width, bottom=INNER,
               color=color, alpha=0.90, zorder=3)

        # Stat label just outside the ring
        label_r = OUTER + 0.13
        ax.text(angle, label_r, label, ha="center", va="center",
                color="#e2e8f0", fontsize=7.5, fontweight="bold",
                rotation=0)

        # Percentile value inside bar
        if pct > 0.15:
            ax.text(angle, INNER + (bar_height - INNER) * 0.55,
                    f"{int(pct*100)}",
                    ha="center", va="center",
                    color="white", fontsize=7, fontweight="bold", zorder=5)

    # Grid rings
    for r in [0.25, 0.5, 0.75, 1.0]:
        ring_r = INNER + r * (OUTER - INNER)
        circle = plt.Circle((0, 0), ring_r, transform=ax.transData._b,
                             fill=False, color="#374151", linewidth=0.6, zorder=0)
        fig.gca().add_artist(circle)

    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_ylim(0, OUTER + 0.35)

    # Unified scout report headings with absolute centering
    fig.suptitle(f"{name}", color="white", fontsize=22, fontweight="bold", y=0.98)
    fig.text(0.5, 0.89, "Position Performance Pizza", color="#94a3b8", fontsize=11, 
             ha="center", fontweight="bold")

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    return _fig_to_b64(fig)
