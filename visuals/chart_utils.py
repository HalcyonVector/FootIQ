"""
Shared helpers for every visuals/*.py chart — dark FootIQ theme + base64
encoding + a title-block layout that actually avoids overlap.

mplsoccer's Pitch.draw() positions its axes directly via fig.add_axes(),
which matplotlib's tight_layout()/rect= does NOT manage (that machinery only
resizes axes created through add_subplot/gridspec). Relying on tight_layout
to "make room" for a suptitle above a pitch axes silently no-ops, so the
title ends up overlapping the pitch's own top edge. layout_pitch_axes()
fixes this by repositioning the pitch axes directly instead.
"""
import io, base64, statistics
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BG_DARK = "#0a0e1a"
BG_PANEL = "#0d1526"
LINE_COLOR = "#374151"


def fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor=fig.get_facecolor(), dpi=110)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return encoded


def layout_pitch_axes(ax, top: float = 0.82, bottom: float = 0.10) -> None:
    """Reserve space above/below a freshly-drawn mplsoccer pitch axes for a
    title block and a bottom legend, by repositioning the axes directly
    (see module docstring for why tight_layout can't do this)."""
    ax.set_position([0.03, bottom, 0.94, top - bottom])


def draw_title(fig, title: str, subtitle: str = None, y_title: float = 0.975, y_subtitle: float = 0.895) -> None:
    fig.suptitle(title, color="white", fontsize=19, fontweight="bold", y=y_title)
    if subtitle:
        fig.text(0.5, y_subtitle, subtitle, color="#94a3b8", fontsize=10.5, ha="center")


def draw_title_block(fig, title: str, subtitle: str = None) -> float:
    """Title + subtitle, positioned by an ABSOLUTE inch offset from the top
    of the figure rather than a fixed fraction of its height — the two
    generic helpers below (generate_stat_bar_chart/generate_histogram_chart)
    vary their own figure height with item count, and a fixed-fraction gap
    (e.g. 0.975 vs 0.905) shrinks to a couple of points on a short 2.4in-tall
    figure, which is nowhere near enough room for a 15.5pt title stacked over
    a 9.5pt subtitle without them visually overlapping. Returns the fraction
    the caller should use as tight_layout's rect top, so the plot area
    starts safely below whichever of title/subtitle was drawn."""
    fig_h = fig.get_figheight()
    title_y = 1 - (0.16 / fig_h)
    fig.suptitle(title, color="white", fontsize=15.5, fontweight="bold", y=title_y, verticalalignment="top")
    if subtitle:
        subtitle_y = 1 - (0.52 / fig_h)
        fig.text(0.5, subtitle_y, subtitle, color="#94a3b8", fontsize=9.5, ha="center", va="top")
        return 1 - (0.78 / fig_h)
    return 1 - (0.40 / fig_h)


# Same red -> orange -> yellow -> green -> blue gradient as app.js's percentileColor(),
# kept in sync so a stat's bar color and its chart marker color always match.
_PCT_STOPS = [(0, (239, 68, 68)), (25, (249, 115, 22)), (50, (234, 179, 8)), (75, (34, 197, 94)), (100, (59, 130, 246))]


def percentile_color(pct: float) -> str:
    pct = max(0, min(100, pct))
    for (t0, c0), (t1, c1) in zip(_PCT_STOPS, _PCT_STOPS[1:]):
        if t0 <= pct <= t1:
            a = (pct - t0) / (t1 - t0)
            r = round(c0[0] + a * (c1[0] - c0[0]))
            g = round(c0[1] + a * (c1[1] - c0[1]))
            b = round(c0[2] + a * (c1[2] - c0[2]))
            return f"#{r:02x}{g:02x}{b:02x}"
    return "#3b82f6"


# ─────────────────────────────────────────────────────────────────────────────
# Shared "companion" chart types — most of Wave 6's new per-tab charts are
# just a different view of numbers a category ALREADY computes (a percentile,
# a count, a share) rather than a fresh pitch-map, so they're built from these
# two generic helpers instead of 20+ bespoke one-off matplotlib functions.
# ─────────────────────────────────────────────────────────────────────────────

def generate_stat_bar_chart(title: str, subtitle: str, items: list[tuple]) -> str:
    """Horizontal bar chart, one bar per item. Each item is
    (label, bar_value_0_100, color, display_text) — bar_value is whatever
    0-100 scale the caller wants drawn (a percentile via percentile_color(),
    or a plain count/share with a fixed per-category color to match that
    tab's map chart legend). display_text is the value actually shown
    (e.g. "62%" or "14 (38%)"), independent of what drives the bar length."""
    n = max(1, len(items))
    fig, ax = plt.subplots(figsize=(7.4, max(2.4, 0.6 * n + 1.1)))
    fig.set_facecolor(BG_DARK)
    ax.set_facecolor(BG_DARK)

    if items:
        labels = [it[0] for it in items]
        values = [max(0.0, min(100.0, it[1])) for it in items]
        colors = [it[2] for it in items]
        texts = [it[3] for it in items]
        y = list(range(len(items)))[::-1]

        ax.barh(y, [100] * len(items), height=0.56, color="#1a2236", zorder=1)
        ax.barh(y, values, height=0.56, color=colors, zorder=2)
        for yi, txt in zip(y, texts):
            ax.text(103, yi, txt, va="center", ha="left", color="white", fontsize=10, fontweight="600", zorder=3)

        ax.set_yticks(y)
        ax.set_yticklabels(labels, color="#cbd5e1", fontsize=10.5)
        ax.set_ylim(-0.6, len(items) - 0.4)
    else:
        ax.text(0.5, 0.5, "No data", transform=ax.transAxes, ha="center", va="center", color="#64748b", fontsize=12)
        ax.set_yticks([])

    ax.set_xlim(0, 132)
    ax.set_xticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)

    top = draw_title_block(fig, title, subtitle)
    plt.tight_layout(rect=[0.02, 0.02, 0.98, top])
    return fig_to_b64(fig)


def generate_histogram_chart(title: str, subtitle: str, values: list, bins: int = 10,
                              unit: str = "", color: str = "#3b82f6", marker: tuple = None) -> str:
    """Distribution chart for raw per-event values (release times, carry
    distances, shot distances...) — a median line is drawn so a single number
    from the stat card (e.g. "Median release: 1.2s") has a visible shape
    behind it instead of being a lone figure. `marker`, if given, is an
    additional (value, label) highlighted in a distinct color — e.g. "this
    player" against a cohort distribution, alongside the median line."""
    fig, ax = plt.subplots(figsize=(7.6, 5.4))
    fig.set_facecolor(BG_DARK)
    ax.set_facecolor(BG_PANEL)

    if values:
        ax.hist(values, bins=bins, color=color, alpha=0.85, edgecolor=BG_DARK, linewidth=0.6, zorder=3)
        median = statistics.median(values)
        ax.axvline(median, color="white", linewidth=1.3, linestyle="--", zorder=4)
        ylim = ax.get_ylim()
        ax.text(median, ylim[1] * 0.97, f" median {median:.1f}{unit}", color="white", fontsize=9,
                ha="left", va="top", fontweight="600", zorder=5)
        if marker is not None:
            mval, mlabel = marker
            ax.axvline(mval, color="#f43f5e", linewidth=1.8, zorder=6)
            ax.text(mval, ylim[1] * 0.80, f" {mlabel}", color="#f43f5e", fontsize=9.5,
                    ha="left", va="top", fontweight="700", zorder=6)
    else:
        ax.text(0.5, 0.5, "No data", transform=ax.transAxes, ha="center", va="center", color="#64748b", fontsize=12)

    for spine in ax.spines.values():
        spine.set_color("#374151")
    ax.tick_params(colors="#94a3b8", labelsize=9)
    if unit:
        ax.set_xlabel(unit, color="#94a3b8", fontsize=9.5)
    ax.set_ylabel("Count", color="#94a3b8", fontsize=9.5)

    top = draw_title_block(fig, title, subtitle)
    plt.tight_layout(rect=[0.02, 0.02, 0.98, top])
    return fig_to_b64(fig)
