"""
Solo player visualizations:
  generate_solo_radar       — filled radar vs benchmark max
  generate_archetype_radar  — archetype polygon radar
  generate_efficiency_chart — actual vs expected goal contribution (wide)
Returns base64 PNG strings.
"""
import io, base64
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

from core.scorer import get_position_config

BG_DARK  = "#0a0e1a"
BG_PANEL = "#111827"
GRID_COL = "#1f2937"


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight",
                facecolor=fig.get_facecolor(), dpi=110)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return encoded


def _pct_color(pct: float) -> str:
    stops = [
        (0.00, (239, 68,  68)),
        (0.25, (249, 115, 22)),
        (0.50, (234, 179,  8)),
        (0.75, ( 34, 197, 94)),
        (1.00, ( 59, 130,246)),
    ]
    pct = max(0.0, min(1.0, pct))
    for i in range(len(stops) - 1):
        t0, c0 = stops[i];  t1, c1 = stops[i + 1]
        if t0 <= pct <= t1:
            a = (pct - t0) / (t1 - t0)
            r = int(c0[0] + a*(c1[0]-c0[0]))
            g = int(c0[1] + a*(c1[1]-c0[1]))
            b = int(c0[2] + a*(c1[2]-c0[2]))
            return f"#{r:02x}{g:02x}{b:02x}"
    return "#3b82f6"


def generate_solo_radar(norm: dict, name: str, color_override: str = None) -> str:
    config   = get_position_config(norm.get("position", "Attacker"))
    labels   = config["labels"]
    metrics  = config["metrics"]
    max_vals = config["max_vals"]

    vals   = [min((norm.get(m, 0) or 0) / mv, 1.0) if mv > 0 else 0.0
              for m, mv in zip(metrics, max_vals)]
    N      = len(labels)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    v_plot = vals + [vals[0]]
    a_plot = angles + [angles[0]]

    fig, ax = plt.subplots(figsize=(7, 7), subplot_kw={"polar": True}, facecolor=BG_DARK)
    ax.set_facecolor(BG_PANEL)

    # Benchmark (max) ring
    ax.fill(a_plot, [1.0] * (N + 1), color="#1e2535", alpha=1.0, zorder=1)
    # Player area
    main_col = color_override if color_override else "#3b82f6"
    ax.fill(a_plot, v_plot, color=main_col, alpha=0.25, zorder=3)
    ax.plot(a_plot, v_plot, color=main_col, linewidth=2.5, zorder=4)
    ax.scatter(angles, vals, color=main_col, s=70, zorder=5)

    ax.set_xticks(angles)
    ax.set_xticklabels(labels, color="#e2e8f0", fontsize=9.5, fontweight="bold")
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["25%", "50%", "75%", "Elite"], color="#4b5563", fontsize=7)
    ax.grid(color=GRID_COL, linewidth=0.8)
    ax.spines["polar"].set_color(GRID_COL)

    fig.suptitle(f"{name} — Performance Radar", color="white",
                 fontsize=13, fontweight="bold", y=1.02)
    return _fig_to_b64(fig)


def generate_archetype_radar(norm: dict, name: str, color_override: str = None) -> str:
    from core.scorer import get_archetype_scores
    scores_dict = get_archetype_scores(norm)
    
    labels  = list(scores_dict.keys())
    values  = list(scores_dict.values())
    N       = len(labels)
    
    angles  = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    v_plot  = values + [values[0]]
    a_plot  = angles + [angles[0]]
    
    # BRAND THEME
    MAIN_COL = color_override if color_override else "#f59e0b" # Amber-500 or custom hex
    
    # Increase figsize and use polar
    # Uniform 8x8 figure for professional scaling
    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={"polar": True}, facecolor=BG_DARK)
    ax.set_facecolor(BG_PANEL)
    
    # Background rings
    ax.fill(a_plot, [1.0] * (N + 1), color="#1e2535", alpha=1.0, zorder=1)
    
    # Player Area
    ax.fill(a_plot, v_plot, color=MAIN_COL, alpha=0.35, zorder=3)
    ax.plot(a_plot, v_plot, color=MAIN_COL, linewidth=3.5, zorder=4)
    ax.scatter(angles, values, color=MAIN_COL, s=100, zorder=5, 
               edgecolors="white", linewidths=1.2)
    
    ax.set_xticks(angles)
    ax.set_xticklabels(labels, color="#fde68a", fontsize=12, fontweight="bold")
    
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["", "", "", ""], color="#4b5563")
    
    ax.grid(color=GRID_COL, linewidth=1.2)
    ax.spines["polar"].set_color(GRID_COL)
    
    # Unified scout report headings with absolute centering
    fig.suptitle(f"{name}", color="white", fontsize=22, fontweight="bold", y=0.98)
    fig.text(0.5, 0.89, "Tactical Profile Archetype", color="#94a3b8", fontsize=11, 
             ha="center", fontweight="bold")

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    return _fig_to_b64(fig)


def generate_efficiency_chart(norm: dict, name: str) -> str:
    """
    Wide landscape chart showing actual vs expected goal contribution.
    Rows spaced with GAP=1.6 so each metric has generous breathing room.
    """
    BLUE   = "#00d4ff"
    PURPLE = "#bf5fff"
    GREEN  = "#00ff88"
    PINK   = "#ff2d78"
    AMBER  = "#ffb800"
    DIM    = "#2d3748"
    MUTED  = "#6b7280"

    g90    = norm.get("goals_p90",      0) or 0
    xg90   = norm.get("xg_p90",         0) or 0
    a90    = norm.get("assists_p90",    0) or 0
    xa90   = norm.get("xa_p90",         0) or 0
    npxg90 = norm.get("npxg_p90",       0) or 0
    xgc90  = norm.get("xg_chain_p90",   0) or 0
    xgb90  = norm.get("xg_buildup_p90", 0) or 0

    has_xg    = xg90 > 0
    has_chain = xgc90 > 0

    # ── Build rows ────────────────────────────────────────────────────────────
    rows = [
        ("Goals / 90",   g90,  xg90,   BLUE,   "xG / 90"),
        ("Assists / 90", a90,  xa90,   PURPLE, "xA / 90"),
    ]
    if npxg90 > 0 and has_xg:
        rows.append(("npG / 90", npxg90, npxg90, GREEN, "npxG / 90"))

    n   = len(rows)
    GAP = 1.6              # vertical units between row centres
    BAR_H = 0.30           # height of each individual bar

    # ── Figure & axes ─────────────────────────────────────────────────────────
    # Height scales with number of rows: 2.8 per row + 1.4 header
    fig_h = n * 2.8 + 1.4
    fig_w = 15 if has_chain else 13

    fig = plt.figure(figsize=(fig_w, fig_h), facecolor=BG_DARK)

    # Reserve top 22% for titles/legend; rest for axes
    T = 0.78   # axes top (fraction)
    B = 0.06   # axes bottom

    if has_chain:
        gs  = fig.add_gridspec(1, 2, width_ratios=[3, 2], wspace=0.10,
                               left=0.06, right=0.97, top=T, bottom=B)
        ax1 = fig.add_subplot(gs[0])
        ax2 = fig.add_subplot(gs[1])
    else:
        ax1 = fig.add_axes([0.06, B, 0.91, T - B])
        ax2 = None

    ax1.set_facecolor(BG_PANEL)

    X_MAX = max((max(r[1], r[2]) for r in rows), default=0.5) * 1.6 or 0.5

    for i, (label, actual, expected, color, exp_label) in enumerate(rows):
        yc = (n - 1 - i) * GAP      # centre of this row group

        # Background track
        ax1.barh(yc, X_MAX * 0.90, BAR_H * 2.6, left=0,
                 color=DIM, alpha=0.22, zorder=1)

        # Expected bar (dim, top of pair)
        if has_xg and expected > 0:
            ye = yc + BAR_H * 0.6
            ax1.barh(ye, expected, BAR_H, color=MUTED, alpha=0.75, zorder=2)
            ax1.text(expected + X_MAX * 0.015, ye,
                     f"{expected:.2f}", va="center",
                     color=MUTED, fontsize=9, fontweight="600")
            ax1.text(X_MAX * 0.89, ye, exp_label,
                     va="center", ha="right",
                     color=MUTED, fontsize=8, style="italic")

        # Actual bar (vivid, bottom of pair)
        ya = yc - BAR_H * 0.6
        ax1.barh(ya, actual, BAR_H, color=color, alpha=0.92, zorder=3, linewidth=0)
        ax1.text(actual + X_MAX * 0.015, ya,
                 f"{actual:.2f}", va="center",
                 color=color, fontsize=10.5, fontweight="800")
        ax1.text(X_MAX * 0.89, ya, label,
                 va="center", ha="right",
                 color="#e2e8f0", fontsize=9.5, fontweight="700")

        # Delta badge (right edge)
        if has_xg and expected > 0:
            delta = actual - expected
            sign  = "+" if delta >= 0 else ""
            dcol  = GREEN if delta >= 0 else PINK
            ax1.text(X_MAX * 0.97, yc, f"{sign}{delta:.2f}",
                     va="center", ha="right",
                     color=dcol, fontsize=10, fontweight="900")

        # Divider between rows
        if i < n - 1:
            ax1.axhline(yc - GAP * 0.48, color=GRID_COL, linewidth=0.7, zorder=0)

    # Legend as text in header (not inside axes — avoids overlap)
    fig.text(0.06, 0.90, "Efficiency & Goal Contribution",
             color="white", fontsize=15, fontweight="900")
    fig.text(0.06, 0.83,
             "Actual output vs statistical expectation per 90 min",
             color="#64748b", fontsize=9.5)
    # Inline legend swatches
    lx = 0.55 if has_chain else 0.70
    fig.text(lx,       0.865, "▌", color=BLUE,  fontsize=14)
    fig.text(lx+0.022, 0.865, "Actual",          color="#94a3b8", fontsize=8.5)
    fig.text(lx+0.075, 0.865, "▌", color=MUTED, fontsize=14)
    fig.text(lx+0.097, 0.865, "Expected (xStat)", color="#94a3b8", fontsize=8.5)

    ax1.set_xlim(0, X_MAX)
    ax1.set_ylim(-GAP * 0.7, (n - 1) * GAP + GAP * 0.7)
    ax1.set_xticks([])
    ax1.set_yticks([])
    for sp in ax1.spines.values():
        sp.set_visible(False)

    # ── Right panel: xG chain ─────────────────────────────────────────────────
    if ax2 is not None:
        ax2.set_facecolor(BG_PANEL)
        chain_rows = [
            ("xG Chain / 90",     xgc90, BLUE),
            ("xG Buildup / 90",   xgb90, GREEN),
            ("xG from Shot / 90", xg90,  AMBER),
        ]
        X2_MAX = max(r[1] for r in chain_rows) * 1.65 or 0.5
        nc = len(chain_rows)
        for j, (lbl, val, col) in enumerate(chain_rows):
            yc2 = (nc - 1 - j) * GAP
            ax2.barh(yc2, X2_MAX * 0.88, BAR_H * 1.8, left=0,
                     color=DIM, alpha=0.22, zorder=1)
            ax2.barh(yc2, val, BAR_H * 1.4, color=col, alpha=0.92, zorder=3)
            ax2.text(val + X2_MAX * 0.025, yc2,
                     f"{val:.2f}", va="center",
                     color=col, fontsize=9.5, fontweight="800")
            ax2.text(-X2_MAX * 0.02, yc2, lbl,
                     va="center", ha="right",
                     color="#cbd5e1", fontsize=8.5, fontweight="600")
            if j < nc - 1:
                ax2.axhline(yc2 - GAP * 0.48, color=GRID_COL, linewidth=0.7, zorder=0)

        ax2.set_xlim(0, X2_MAX)
        ax2.set_ylim(-GAP * 0.7, (nc - 1) * GAP + GAP * 0.7)
        ax2.set_xticks([])
        ax2.set_yticks([])
        for sp in ax2.spines.values():
            sp.set_visible(False)

        rx = 0.655
        fig.text(rx, 0.90, "xG Chain Breakdown",
                 color="white", fontsize=13, fontweight="800")
        fig.text(rx, 0.83, "Involvement in all chance creation",
                 color="#64748b", fontsize=8.5)

    return _fig_to_b64(fig)
