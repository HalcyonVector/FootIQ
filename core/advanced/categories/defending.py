"""
Defending Profile — by zone (box / channel / flank), using the acting
player's own attacking-direction-normalized coordinates (x=0 own goal),
mirrored in geometry.defensive_zone() to reuse the same in_box/half_space
tests as the attacking categories.
"""

from core.advanced import geometry as g, qualifiers as q
from core.advanced.accumulate import PlayerAcc

P90_KEYS = {
    "def_tackles_total", "def_interceptions_total", "def_blocks_total",
    "def_clearances_total", "def_recoveries_total",
    "def_box_actions", "def_box_tackles_count", "def_box_interceptions_count",
    "def_box_blocks_count", "def_box_clearances_count", "def_clearance_distance_m",
    "def_box_aerials_won_count", "def_channel_actions", "def_channel_tackles_count",
    "def_channel_interceptions_count", "def_channel_recoveries_count",
    "def_flank_actions", "def_flank_tackles_count", "def_flank_interceptions_count",
    "def_flank_recoveries_count", "def_flank_clearances_count",
    "def_fouls_box_count", "def_fouls_channel_count",
}


def compute_defending(events: list[dict], rosters: list[dict]) -> dict:
    acc = PlayerAcc()

    for e in events:
        pid = e["player_id"]
        if pid is None:
            continue
        etype = e["type"]
        x, y = e.get("x"), e.get("y")
        zone = g.defensive_zone(x, y) if x is not None and y is not None else "other"

        if etype == "Tackle":
            acc.add(pid, "def_tackles")
            won = e["outcome_type"] == "Successful"
            if won:
                acc.add(pid, "def_tackles_won")
            if zone == "box":
                acc.add(pid, "def_box_tackles")
                if won:
                    acc.add(pid, "def_box_tackles_won")
            elif zone == "channel":
                acc.add(pid, "def_channel_tackles")
                if won:
                    acc.add(pid, "def_channel_tackles_won")
            elif zone == "flank":
                acc.add(pid, "def_flank_tackles")
                if won:
                    acc.add(pid, "def_flank_tackles_won")

        elif etype == "Interception":
            acc.add(pid, "def_interceptions")
            if zone == "box":
                acc.add(pid, "def_box_interceptions")
            elif zone == "channel":
                acc.add(pid, "def_channel_interceptions")
            elif zone == "flank":
                acc.add(pid, "def_flank_interceptions")

        elif etype in ("BlockedPass",):
            acc.add(pid, "def_blocks")
            if zone == "box":
                acc.add(pid, "def_box_blocks")

        elif etype == "Clearance":
            acc.add(pid, "def_clearances")
            qm = q.qmap(e["qualifiers"])
            length = q.qualifier_float(qm, "Length")
            if length is not None:
                acc.add(pid, "def_clearance_distance_m", g.units_to_meters(length))
            if zone == "box":
                acc.add(pid, "def_box_clearances")
            elif zone == "flank":
                acc.add(pid, "def_flank_clearances")

        elif etype == "BallRecovery":
            acc.add(pid, "def_recoveries_total")
            if zone == "channel":
                acc.add(pid, "def_channel_recoveries")
            elif zone == "flank":
                acc.add(pid, "def_flank_recoveries")

        elif etype == "Aerial":
            if zone == "box":
                acc.add(pid, "def_box_aerials")
                if e["outcome_type"] == "Successful":
                    acc.add(pid, "def_box_aerials_won")

        elif etype == "Foul":
            if zone == "box":
                acc.add(pid, "def_fouls_box")
            elif zone == "channel":
                acc.add(pid, "def_fouls_channel")

    return acc.to_dict()


def finalize_defending(totals: dict) -> dict:
    def pct(num, den, min_sample=1):
        return round(100 * num / den, 1) if den >= min_sample else None

    out = {}
    for pid, t in totals.items():
        out[pid] = {
            "def_tackles_total": t.get("def_tackles", 0),
            "def_tackle_success_pct": pct(t.get("def_tackles_won", 0), t.get("def_tackles", 0), 10),
            "def_interceptions_total": t.get("def_interceptions", 0),
            "def_blocks_total": t.get("def_blocks", 0),
            "def_clearances_total": t.get("def_clearances", 0),
            "def_recoveries_total": t.get("def_recoveries_total", 0),
            "def_box_actions": t.get("def_box_tackles", 0) + t.get("def_box_interceptions", 0) + t.get("def_box_blocks", 0) + t.get("def_box_clearances", 0),
            "def_box_tackles_count": t.get("def_box_tackles", 0),
            "def_box_tackle_success_pct": pct(t.get("def_box_tackles_won", 0), t.get("def_box_tackles", 0), 10),
            "def_box_interceptions_count": t.get("def_box_interceptions", 0),
            "def_box_blocks_count": t.get("def_box_blocks", 0),
            "def_box_clearances_count": t.get("def_box_clearances", 0),
            "def_clearance_distance_m": round(t.get("def_clearance_distance_m", 0), 1),
            "def_box_aerials_won_count": t.get("def_box_aerials_won", 0),
            "def_box_aerial_success_pct": pct(t.get("def_box_aerials_won", 0), t.get("def_box_aerials", 0), 10),
            "def_channel_actions": t.get("def_channel_tackles", 0) + t.get("def_channel_interceptions", 0) + t.get("def_channel_recoveries", 0),
            "def_channel_tackles_count": t.get("def_channel_tackles", 0),
            "def_channel_tackle_success_pct": pct(t.get("def_channel_tackles_won", 0), t.get("def_channel_tackles", 0), 10),
            "def_channel_interceptions_count": t.get("def_channel_interceptions", 0),
            "def_channel_recoveries_count": t.get("def_channel_recoveries", 0),
            "def_flank_actions": t.get("def_flank_tackles", 0) + t.get("def_flank_interceptions", 0) + t.get("def_flank_recoveries", 0),
            "def_flank_tackles_count": t.get("def_flank_tackles", 0),
            "def_flank_tackle_success_pct": pct(t.get("def_flank_tackles_won", 0), t.get("def_flank_tackles", 0), 10),
            "def_flank_interceptions_count": t.get("def_flank_interceptions", 0),
            "def_flank_recoveries_count": t.get("def_flank_recoveries", 0),
            "def_flank_clearances_count": t.get("def_flank_clearances", 0),
            "def_fouls_box_count": t.get("def_fouls_box", 0),
            "def_fouls_channel_count": t.get("def_fouls_channel", 0),
        }
    return out
