"""
Carrying Profile — two charts, always shown side by side in a half-width
slot, so both keep their own baked-in text minimal (just a short title) and
report their counts back as a `stats` dict instead — the caller renders that
as normal HTML text, which stays legible at any size unlike raster text
squeezed into a ~300px-wide image.

generate_carrying_chart() plots progressive carries as vectors, colored by
what the player did immediately after (progressive pass / take-on won/lost /
nothing). generate_carry_angle_rose() is a compass-style polar chart of carry
direction bias: Forward (right) vs Infield (up) vs Back (left) vs Outfield
(down), mirroring Carrying Profile's own "Angle Bias Index" stat.
"""
import math
import statistics

import matplotlib.pyplot as plt
from mplsoccer import Pitch

from visuals.chart_utils import (
    BG_DARK, BG_PANEL, LINE_COLOR, fig_to_b64, layout_pitch_axes, draw_title,
    generate_histogram_chart,
)

PROG_COLOR = "#ef4444"
FOLLOWUP_PASS_COLOR = "#22c55e"
TAKEON_WON_COLOR = "#3b82f6"
TAKEON_LOST_COLOR = "#9ca3af"


def generate_carrying_chart(player_name: str, team: str, season: str, carries: list[dict],
                             show: tuple = ("prog_pass", "takeon_won", "takeon_lost")) -> tuple:
    pitch = Pitch(pitch_type="opta", pitch_color=BG_PANEL, line_color=LINE_COLOR, linewidth=1.2, half=False)
    fig, ax = pitch.draw(figsize=(7.6, 6.4))
    fig.set_facecolor(BG_DARK)
    layout_pitch_axes(ax, top=0.87, bottom=0.04)

    prog_n = 0
    counts = {"prog_pass": 0, "takeon_won": 0, "takeon_lost": 0}
    for c in carries:
        if None in (c["start_x"], c["start_y"], c["end_x"], c["end_y"]):
            continue
        if not c["progressive"]:
            continue
        prog_n += 1
        pitch.lines(c["start_x"], c["start_y"], c["end_x"], c["end_y"], ax=ax, color=PROG_COLOR,
                    lw=1.6, linestyle="--", alpha=0.75, zorder=2)
        followup = c.get("followup", "none")
        if followup in counts:
            counts[followup] += 1
        if followup == "prog_pass" and "prog_pass" in show:
            pitch.scatter(c["end_x"], c["end_y"], ax=ax, color=FOLLOWUP_PASS_COLOR, s=44, zorder=4,
                          edgecolors="white", linewidth=0.4)
        elif followup == "takeon_won" and "takeon_won" in show:
            pitch.scatter(c["end_x"], c["end_y"], ax=ax, color=TAKEON_WON_COLOR, s=54, zorder=4,
                          edgecolors="white", linewidth=0.5)
        elif followup == "takeon_lost" and "takeon_lost" in show:
            pitch.scatter(c["end_x"], c["end_y"], ax=ax, color=TAKEON_LOST_COLOR, s=54, zorder=4,
                          edgecolors="white", linewidth=0.5)

    fig.suptitle("Progressive Carries", color="white", fontsize=17, fontweight="bold", y=0.975)
    stats = {"prog_carries": prog_n, "prog_pass_after": counts["prog_pass"],
             "takeon_won_after": counts["takeon_won"], "takeon_lost_after": counts["takeon_lost"]}
    return fig_to_b64(fig), stats


def generate_carry_angle_rose(player_name: str, carries: list[dict]) -> tuple:
    angles = []
    for c in carries:
        if not c["progressive"] or None in (c["start_x"], c["start_y"], c["end_x"], c["end_y"]):
            continue
        dx = c["end_x"] - c["start_x"]
        toward_center_sign = 1 if c["start_y"] < 50 else -1
        dy = (c["end_y"] - c["start_y"]) * toward_center_sign
        if dx == 0 and dy == 0:
            continue
        angles.append(math.atan2(dy, dx))

    fig = plt.figure(figsize=(6.4, 6.4))
    fig.set_facecolor(BG_DARK)
    ax = fig.add_subplot(111, projection="polar")
    ax.set_facecolor(BG_DARK)
    ax.set_theta_zero_location("E")
    ax.set_theta_direction(1)

    abi = 0.0
    if angles:
        mean_angle = math.atan2(sum(math.sin(a) for a in angles), sum(math.cos(a) for a in angles))
        spread = max(0.25, min(statistics.pstdev(angles) if len(angles) > 1 else 0.4, 1.1))
        ax.fill_between([mean_angle - spread, mean_angle + spread], 0, 1, color=PROG_COLOR, alpha=0.55, zorder=2)
        ax.annotate("", xy=(mean_angle, 0.95), xytext=(mean_angle, 0),
                    arrowprops=dict(facecolor=PROG_COLOR, edgecolor=PROG_COLOR, width=2.6, headwidth=11), zorder=3)
        abi = round(sum(math.sin(a) for a in angles) / len(angles), 2)

    ax.set_ylim(0, 1)
    ax.set_yticklabels([])
    ax.set_xticks([0, math.pi / 2, math.pi, 3 * math.pi / 2])
    ax.set_xticklabels(["Forward", "Infield", "Back", "Outfield"], color="#94a3b8", fontsize=12.5)
    ax.grid(color="#374151", alpha=0.5)
    ax.spines["polar"].set_color("#374151")

    label = "infield" if abi > 0.05 else ("outfield" if abi < -0.05 else "neutral")
    fig.suptitle("Carry Angle Rose", color="white", fontsize=17, fontweight="bold", y=0.975)
    stats = {"abi": abi, "abi_label": label}
    return fig_to_b64(fig), stats


def generate_carry_distance_chart(player_name: str, team: str, season: str, carries: list[dict]) -> str:
    """Distribution of carry distances (meters) — how far this player typically
    drives the ball per carry, not just the mean shown on the stat card."""
    values = []
    for c in carries:
        if None in (c["start_x"], c["start_y"], c["end_x"], c["end_y"]):
            continue
        dist_units = ((c["end_x"] - c["start_x"]) ** 2 + (c["end_y"] - c["start_y"]) ** 2) ** 0.5
        values.append(dist_units / 100.0 * 105.0)  # 0-100 pitch units -> meters, same conversion as geometry.units_to_meters
    return generate_histogram_chart("Carry Distance Distribution", f"{team} | {season}    Sample: {len(values)} carries",
                                     values, bins=12, unit="m", color=PROG_COLOR)


def generate_takeon_chart(player_name: str, team: str, season: str, takeons: list[dict]) -> str:
    """Every standalone take-on attempt at its location, won vs lost — distinct
    from the progressive-carry map's "followup" take-ons (those only capture a
    take-on immediately after a carry, not every attempt on the ball)."""
    pitch = Pitch(pitch_type="opta", pitch_color=BG_PANEL, line_color=LINE_COLOR, linewidth=1.2, half=False)
    fig, ax = pitch.draw(figsize=(11, 7.3))
    fig.set_facecolor(BG_DARK)
    layout_pitch_axes(ax, top=0.80, bottom=0.11)

    won_n = lost_n = 0
    for t in takeons:
        if t["x"] is None or t["y"] is None:
            continue
        if t["outcome"] == "won":
            won_n += 1
            pitch.scatter(t["x"], t["y"], ax=ax, marker="o", color=TAKEON_WON_COLOR, s=60, zorder=4,
                          edgecolors="white", linewidth=0.4)
        else:
            lost_n += 1
            pitch.scatter(t["x"], t["y"], ax=ax, marker="o", facecolors="none", edgecolors=TAKEON_LOST_COLOR,
                          s=55, linewidth=1.1, zorder=3)

    n = won_n + lost_n
    win_pct = round(100 * won_n / n) if n else 0
    subtitle = f"Take-On Locations | {team} | {season}    Won: {won_n}    Lost: {lost_n}    Success: {win_pct}%"
    draw_title(fig, player_name, subtitle)

    handles = [
        plt.Line2D([0], [0], marker="o", color="none", markerfacecolor=TAKEON_WON_COLOR, markersize=9, markeredgecolor="white"),
        plt.Line2D([0], [0], marker="o", color="none", markerfacecolor="none", markersize=9, markeredgecolor=TAKEON_LOST_COLOR),
    ]
    fig.legend(handles, [f"Won: {won_n}", f"Lost: {lost_n}"], loc="lower center", ncol=2,
               frameon=False, labelcolor="#cbd5e1", fontsize=8.5, bbox_to_anchor=(0.5, 0.02))
    return fig_to_b64(fig)
