"""Tempo Control — injector (speeds play up) vs reset (settles it) actions."""
import matplotlib.pyplot as plt
from mplsoccer import Pitch

from visuals.chart_utils import (
    BG_DARK, BG_PANEL, LINE_COLOR, fig_to_b64, layout_pitch_axes, draw_title,
    generate_stat_bar_chart, generate_histogram_chart,
)

STYLE = {
    "injector_pass":  {"color": "#ef4444", "label": "Injector Pass"},
    "injector_carry": {"color": "#22c55e", "label": "Injector Carry", "dashed": True},
    "reset_pass":     {"color": "#3b82f6", "label": "Reset Pass"},
}


def generate_tempo_chart(player_name: str, team: str, season: str, actions: list[dict]) -> str:
    pitch = Pitch(pitch_type="opta", pitch_color=BG_PANEL, line_color=LINE_COLOR, linewidth=1.2, half=False)
    fig, ax = pitch.draw(figsize=(11, 7.3))
    fig.set_facecolor(BG_DARK)
    layout_pitch_axes(ax, top=0.80, bottom=0.11)

    counts = {k: 0 for k in STYLE}
    for a in actions:
        if None in (a["x"], a["y"], a["end_x"], a["end_y"]):
            continue
        style = STYLE.get(a["kind"])
        if not style:
            continue
        counts[a["kind"]] += 1
        pitch.lines(a["x"], a["y"], a["end_x"], a["end_y"], ax=ax, color=style["color"], lw=1.3,
                    linestyle="--" if style.get("dashed") else "-", alpha=0.7, zorder=2)

    injectors = counts["injector_pass"] + counts["injector_carry"]
    resets = counts["reset_pass"]
    subtitle = f"Tempo Control | {team} | {season}    Injectors: {injectors}    Resets: {resets}"
    draw_title(fig, player_name, subtitle)

    handles = [plt.Line2D([0], [0], color=v["color"], lw=2.2, linestyle="--" if v.get("dashed") else "-") for v in STYLE.values()]
    labels = [f"{v['label']}: {counts[k]}" for k, v in STYLE.items()]
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False,
               labelcolor="#cbd5e1", fontsize=8.5, bbox_to_anchor=(0.5, 0.02))
    return fig_to_b64(fig)


def generate_tempo_release_chart(player_name: str, team: str, season: str, actions: list[dict]) -> str:
    """Distribution of pass release times across all open-play passes (not
    just the ones tagged injector/reset) — the raw shape behind the median
    release stat and the quick-release-% stat."""
    values = [a["release_s"] for a in actions if a.get("release_s") is not None]
    return generate_histogram_chart("Release-Time Distribution", f"{team} | {season}    Sample: {len(values)} passes",
                                     values, bins=14, unit="s", color=STYLE["reset_pass"]["color"])


def generate_tempo_balance_chart(player_name: str, team: str, season: str, actions: list[dict]) -> str:
    """Injector vs reset share of all tempo-tagged actions."""
    injectors = sum(1 for a in actions if a["kind"] in ("injector_pass", "injector_carry"))
    resets = sum(1 for a in actions if a["kind"] == "reset_pass")
    n = injectors + resets
    items = [
        ("Injectors", 100 * injectors / n if n else 0, STYLE["injector_pass"]["color"],
         f"{injectors} ({round(100*injectors/n) if n else 0}%)"),
        ("Resets", 100 * resets / n if n else 0, STYLE["reset_pass"]["color"],
         f"{resets} ({round(100*resets/n) if n else 0}%)"),
    ]
    return generate_stat_bar_chart("Injector vs Reset Balance", f"{team} | {season}    Total: {n}", items)
