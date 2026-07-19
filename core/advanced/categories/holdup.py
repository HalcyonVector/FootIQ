"""
Hold-Up Play — a "hold episode" is the gap between when the ball arrives at
a player (the DELIVERY: usually a teammate's pass, sometimes a loose ball
off an opponent action) and when that same player finally releases it
(pass/shot/take-on/dispossession), when that gap is 5-20 seconds.

Two things have to both be true for a span to count as a genuine hold:
1. No one else touched the ball in between — enforced by walking strictly
   ADJACENT events in the raw stream (skipping only administrative types),
   stopping the instant a different player's touch appears. This is what
   stops a loose ball that bounces around for a minute before coincidentally
   returning to the same player from being misread as one continuous hold.
2. Duration is measured from the DELIVERY event (the pass/action immediately
   BEFORE the player's own chain starts) to the chain's last touch — NOT
   from the player's own first touch to their own last touch. Opta never
   logs a separate "reception" event, so the extremely common "receive once,
   stand there under pressure, release once" pattern is a chain of length 1
   — measuring self-to-self duration for that case is always exactly zero,
   which is why an earlier version of this module undercounted by roughly
   two orders of magnitude. Measuring delivery-to-release fixes it while
   keeping the continuity guarantee from (1) intact.

Verified against real data: this produces ~8 episodes/match for Bruno
Fernandes (PL 2025-26, 35 matches, final/middle/defensive ≈ 20%/60%/20%
split) — in line with the reference app's own proportions, vs. ~0.03/match
for the old adjacency-only-duration version and an implausible ~18/match
for an even simpler "gap since the player's own last event of any kind"
version that didn't require possession continuity.

Per the reference glossary, detection runs across the WHOLE pitch and each
qualifying episode is classified into a zone (final/middle/defensive third)
by where the hold STARTED (the delivery's arrival point). "Final third" is
the primary/default view — a centre-back calmly holding the ball in his own
defensive third under no pressure isn't doing the same thing this category
is trying to capture — but Middle Third and Whole Pitch are computed too so
a deep-dropping playmaker's holds aren't invisible just because they happen
outside the final third.
"""

from core.advanced import geometry as g, qualifiers as q, timing
from core.advanced.accumulate import PlayerAcc
from core.advanced.carries import NON_TOUCH_TYPES
from core.advanced.possession_chains import trace_forward_by_time

MIN_HOLD_SECONDS = 5.0
MAX_HOLD_SECONDS = 20.0            # beyond this, treat as an unrelated later touch, not one continuous hold
DEFENSIVE_THIRD_MAX_X = 100 / 3    # 0 - 33.3: defensive third
FINAL_THIRD_X = 200 / 3            # 33.3 - 66.7: middle third; >= 66.7: final third

OPPONENT_SHOT_TYPES = ("MissedShots", "SavedShot", "Goal", "ShotOnPost")
ZONES = ("final", "middle", "defensive")

# A loss only counts as "dangerous" if the opponent turns it into a shot OR
# gets the ball into the box within this window — gating on "shot" alone
# (the original definition) made this metric render 0% for ~75% of the
# whole league (a shot within 10s of any single lost hold is a rare event
# even for a bad loss), which fails the same "will it actually show
# meaningful values" bar the rest of these metrics are held to. Box entry is
# the standard looser proxy for "created something dangerous" used across
# public transition-analysis work when a literal shot is too rare a signal.
DANGEROUS_WINDOW_SECONDS = 15.0


def _is_dangerous_aftermath(aftermath: list[dict], team_id) -> bool:
    for te in aftermath:
        if te.get("team_id") == team_id:
            continue
        if te["type"] in OPPONENT_SHOT_TYPES:
            return True
        x, y = te.get("x"), te.get("y")
        if x is not None and y is not None and g.in_box(x, y):
            return True
        if te["type"] == "Pass":
            ex, ey = te.get("end_x"), te.get("end_y")
            if ex is not None and ey is not None and g.in_box(ex, ey):
                return True
    return False

P90_KEYS = {"hu_final_episodes", "hu_middle_episodes", "hu_whole_episodes"}


def zone_of(x: float) -> str:
    if x >= FINAL_THIRD_X:
        return "final"
    if x >= DEFENSIVE_THIRD_MAX_X:
        return "middle"
    return "defensive"


def _find_hold(events: list[dict], i: int):
    """From event i (the first touch of a possible new hold), returns
    (x0, y0, delivery_time, last_event, last_index) or None if event i
    doesn't start a genuine new hold (mid-chain continuation, no prior
    delivery event, or missing coordinates)."""
    e = events[i]
    pid, team_id = e.get("player_id"), e.get("team_id")

    k = i - 1
    while k >= 0 and events[k]["type"] in NON_TOUCH_TYPES:
        k -= 1
    if k < 0:
        return None
    delivery = events[k]
    if delivery.get("player_id") == pid:
        return None  # continues a chain whose true start was already processed

    if delivery["type"] == "Pass" and delivery.get("end_x") is not None and delivery.get("end_y") is not None:
        x0, y0 = delivery["end_x"], delivery["end_y"]
    else:
        x0, y0 = delivery.get("x"), delivery.get("y")
    if x0 is None or y0 is None:
        return None
    delivery_t = timing.event_seconds(delivery)

    last, last_idx = e, i
    j = i + 1
    while j < len(events):
        nxt = events[j]
        if nxt["type"] in NON_TOUCH_TYPES:
            j += 1
            continue
        if nxt.get("team_id") != team_id:
            # A failed opponent tackle or a foul doesn't actually take the
            # ball away — tolerate it (as pressure endured) without ending
            # the hold. Anything else from the opponent (a successful
            # tackle, interception, block...) genuinely does end it.
            if (nxt["type"] == "Tackle" and nxt.get("outcome_type") == "Unsuccessful") or nxt["type"] == "Foul":
                j += 1
                continue
            break
        if nxt.get("player_id") != pid:
            break
        if timing.event_seconds(nxt) - timing.event_seconds(last) > MAX_HOLD_SECONDS:
            break
        last, last_idx = nxt, j
        j += 1

    return x0, y0, delivery_t, last, last_idx


def compute_holdup(events: list[dict]) -> dict:
    acc = PlayerAcc()

    for i, e in enumerate(events):
        if e["type"] in NON_TOUCH_TYPES:
            continue
        pid, team_id = e.get("player_id"), e.get("team_id")
        if pid is None or team_id is None:
            continue

        found = _find_hold(events, i)
        if found is None:
            continue
        x0, y0, delivery_t, last, last_idx = found
        duration = timing.event_seconds(last) - delivery_t
        if not (MIN_HOLD_SECONDS <= duration <= MAX_HOLD_SECONDS):
            continue

        zone = zone_of(x0)
        acc.add(pid, f"hu_episodes_{zone}")

        lost = last["type"] == "Dispossessed" or (last["type"] == "Pass" and last["outcome_type"] == "Unsuccessful")
        if not lost:
            acc.add(pid, f"hu_retained_{zone}")

        if last["type"] == "Pass" and last["outcome_type"] == "Successful":
            ex, ey = last.get("end_x"), last.get("end_y")
            qm = q.qmap(last["qualifiers"])
            if None not in (ex, ey) and not q.has_qualifier(qm, q.CROSS_Q) and g.is_progressive_action((x0, y0), (ex, ey)):
                acc.add(pid, f"hu_prog_release_{zone}")
        elif last["type"] in OPPONENT_SHOT_TYPES:
            acc.add(pid, f"hu_shot_from_hold_{zone}")

        xl, yl = last.get("x"), last.get("y")
        if xl is not None and yl is not None and g.is_progressive_action((x0, y0), (xl, yl)):
            acc.add(pid, f"hu_prog_carry_{zone}")

        for te in events[i:last_idx + 1]:
            if te["type"] == "Tackle" and te.get("team_id") != team_id and te["outcome_type"] == "Unsuccessful":
                acc.add(pid, f"hu_tackles_avoided_{zone}")
            if te["type"] == "Foul" and te.get("team_id") != team_id:
                acc.add(pid, f"hu_fouls_won_{zone}")

        if lost:
            aftermath = trace_forward_by_time(events, last_idx, window_seconds=DANGEROUS_WINDOW_SECONDS)
            if _is_dangerous_aftermath(aftermath, team_id):
                acc.add(pid, f"hu_dangerous_loss_{zone}")

    return acc.to_dict()


def finalize_holdup(totals: dict) -> dict:
    def pct(num, den, min_n=10):
        return round(100 * num / den, 1) if den >= min_n else None

    out = {}
    for pid, t in totals.items():
        # Per-zone raw sums, then "whole" = final + middle + defensive (each
        # episode belongs to exactly one zone, so summing is exact).
        by_zone = {}
        for zone in ZONES:
            by_zone[zone] = {
                "episodes": t.get(f"hu_episodes_{zone}", 0),
                "retained": t.get(f"hu_retained_{zone}", 0),
                "prog_release": t.get(f"hu_prog_release_{zone}", 0),
                "prog_carry": t.get(f"hu_prog_carry_{zone}", 0),
                "shot_from_hold": t.get(f"hu_shot_from_hold_{zone}", 0),
                "fouls_won": t.get(f"hu_fouls_won_{zone}", 0),
                "tackles_avoided": t.get(f"hu_tackles_avoided_{zone}", 0),
                "dangerous_loss": t.get(f"hu_dangerous_loss_{zone}", 0),
            }
        whole = {k: sum(by_zone[z][k] for z in ZONES) for k in by_zone["final"]}

        entry = {}
        for view_key, zd in (("final", by_zone["final"]), ("middle", by_zone["middle"]), ("whole", whole)):
            ep = zd["episodes"]
            p = f"hu_{view_key}"
            entry[f"{p}_episodes"] = ep
            entry[f"{p}_retention_pct"] = pct(zd["retained"], ep)
            entry[f"{p}_prog_release_pct"] = pct(zd["prog_release"], ep)
            entry[f"{p}_prog_carry_pct"] = pct(zd["prog_carry"], ep)
            entry[f"{p}_shot_from_hold_pct"] = pct(zd["shot_from_hold"], ep)
            entry[f"{p}_fouls_won_per_hold"] = round(zd["fouls_won"] / ep, 2) if ep >= 10 else None
            entry[f"{p}_tackles_avoided_per_hold"] = round(zd["tackles_avoided"] / ep, 2) if ep >= 10 else None
            entry[f"{p}_dangerous_loss_pct"] = pct(zd["dangerous_loss"], ep)
        out[pid] = entry
    return out
