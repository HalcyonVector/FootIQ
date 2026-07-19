"""
Passing Profile pass map — every open-play pass plotted origin -> end,
colored by progressive/into-box/completed/unsuccessful. `mode` mirrors the
reference app's two views: "progressive" shows only progressive+into-box
passes, "all" shows every open-play pass.
"""
import matplotlib.pyplot as plt
from mplsoccer import Pitch

from core.advanced.geometry import zone_third
from visuals.chart_utils import (
    BG_DARK, BG_PANEL, LINE_COLOR, fig_to_b64, layout_pitch_axes, draw_title,
    generate_stat_bar_chart, generate_histogram_chart,
)

BOX_COLOR = "#3b82f6"
PROG_COLOR = "#22c55e"
PASS_COLOR = "#64748b"
UNSUCCESSFUL_COLOR = "#374151"


def generate_passing_chart(player_name: str, team: str, season: str, passes: list[dict], mode: str = "progressive") -> str:
    pitch = Pitch(pitch_type="opta", pitch_color=BG_PANEL, line_color=LINE_COLOR, linewidth=1.2, half=False)
    fig, ax = pitch.draw(figsize=(11, 7.3))
    fig.set_facecolor(BG_DARK)
    layout_pitch_axes(ax, top=0.80, bottom=0.11)

    prog_n = into_box_n = comp_n = uns_n = 0
    for p in passes:
        if None in (p["x"], p["y"], p["end_x"], p["end_y"]):
            continue
        if p["into_box"]:
            into_box_n += 1
        elif p["progressive"]:
            prog_n += 1
        elif p["completed"]:
            comp_n += 1
        else:
            uns_n += 1
        if mode == "progressive" and not (p["progressive"] or p["into_box"]):
            continue

        if p["into_box"]:
            color, lw, z = BOX_COLOR, 1.6, 4
        elif p["progressive"]:
            color, lw, z = PROG_COLOR, 1.4, 3
        elif p["completed"]:
            color, lw, z = PASS_COLOR, 0.9, 2
        else:
            color, lw, z = UNSUCCESSFUL_COLOR, 0.7, 1
        pitch.lines(p["x"], p["y"], p["end_x"], p["end_y"], ax=ax, color=color, lw=lw, alpha=0.75, zorder=z)
        pitch.scatter(p["x"], p["y"], ax=ax, color=color, s=6, alpha=0.8, zorder=z + 1)

    subtitle = f"Passing Map | {team} | {season}    Passes: {len(passes)}    Prog: {prog_n}    Into box: {into_box_n}"
    draw_title(fig, player_name, subtitle)

    handles = [plt.Line2D([0], [0], color=c, lw=2.5) for c in (BOX_COLOR, PROG_COLOR, PASS_COLOR, UNSUCCESSFUL_COLOR)]
    labels = [f"Into box: {into_box_n}", f"Progressive: {prog_n}", f"Completed: {comp_n}", f"Unsuccessful: {uns_n}"]
    fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False,
               labelcolor="#cbd5e1", fontsize=8.5, bbox_to_anchor=(0.5, 0.02))
    return fig_to_b64(fig)


def generate_pass_outcome_chart(player_name: str, team: str, season: str, passes: list[dict]) -> str:
    """Share-of-attempts breakdown: Into box / Progressive / Completed / Unsuccessful —
    same buckets and colors as the pass map, just as a standalone comparison bar."""
    n = len(passes)
    into_box_n = sum(1 for p in passes if p["into_box"])
    prog_n = sum(1 for p in passes if p["progressive"] and not p["into_box"])
    comp_n = sum(1 for p in passes if p["completed"] and not p["progressive"] and not p["into_box"])
    uns_n = n - into_box_n - prog_n - comp_n

    items = [
        ("Into box", 100 * into_box_n / n if n else 0, BOX_COLOR, f"{into_box_n} ({round(100*into_box_n/n) if n else 0}%)"),
        ("Progressive", 100 * prog_n / n if n else 0, PROG_COLOR, f"{prog_n} ({round(100*prog_n/n) if n else 0}%)"),
        ("Completed", 100 * comp_n / n if n else 0, PASS_COLOR, f"{comp_n} ({round(100*comp_n/n) if n else 0}%)"),
        ("Unsuccessful", 100 * uns_n / n if n else 0, UNSUCCESSFUL_COLOR, f"{uns_n} ({round(100*uns_n/n) if n else 0}%)"),
    ]
    return generate_stat_bar_chart("Pass Outcome Breakdown", f"{team} | {season}    Total attempts: {n}", items)


def generate_release_time_chart(player_name: str, team: str, season: str, passes: list[dict]) -> str:
    """Distribution of release times (gap between a player's prior touch and
    this pass) — the raw shape behind the stat card's median release stat."""
    values = [p["release_s"] for p in passes if p.get("release_s") is not None]
    return generate_histogram_chart("Pass Release-Time Distribution", f"{team} | {season}    Sample: {len(values)} passes",
                                     values, bins=14, unit="s", color=PASS_COLOR)


THIRD_COLORS = {"def": "#3b82f6", "mid": "#eab308", "att": "#22c55e"}
THIRD_LABELS = {"def": "Defensive Third", "mid": "Middle Third", "att": "Attacking Third"}


def generate_pass_zone_chart(player_name: str, team: str, season: str, passes: list[dict]) -> str:
    """Which third of the pitch this player's passes are played FROM — a
    deliberately different angle from the Pass Map (not another pitch
    diagram of the same lines/dots), and one that actually shifts with the
    progressive/all filter: a deep-lying passer's "progressive only" view
    skews defensive/middle third, while their full "all passes" view is
    dominated by short middle-third circulation."""
    counts = {"def": 0, "mid": 0, "att": 0}
    for p in passes:
        if p["x"] is None:
            continue
        counts[zone_third(p["x"])] += 1
    n = sum(counts.values())
    items = [(THIRD_LABELS[z], 100 * counts[z] / n if n else 0, THIRD_COLORS[z],
              f"{counts[z]} ({round(100*counts[z]/n) if n else 0}%)") for z in ("def", "mid", "att")]
    return generate_stat_bar_chart("Pass Origin by Third", f"{team} | {season}    Total: {n}", items)
