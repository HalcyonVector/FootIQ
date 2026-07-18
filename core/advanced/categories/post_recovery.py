"""
Post-Recovery — what a player does in the action(s) immediately after
winning the ball back. Uses the same "next event, same player, strictly
adjacent" adjacency test as carries.py to find the recovering player's
resulting action (or chain: recovery -> carry -> pass).
"""

from core.advanced import geometry as g, qualifiers as q
from core.advanced.accumulate import PlayerAcc
from core.advanced.carries import NON_TOUCH_TYPES

P90_KEYS = {"pr_recoveries", "pr_prog_passes_off_recovery", "pr_prog_carries_off_recovery"}


def compute_post_recovery(events: list[dict]) -> dict:
    acc = PlayerAcc()

    for i, e in enumerate(events):
        if e["type"] != "BallRecovery":
            continue
        pid = e["player_id"]
        if pid is None or e.get("x") is None or e.get("y") is None:
            continue
        acc.add(pid, "pr_recoveries")

        # Walk forward through the recovering player's own adjacent touches
        # (skipping admin event types) to find what they did with it.
        cur = e
        chain_had_carry = False
        j = i + 1
        next_own = None
        while j < len(events):
            nxt = events[j]
            if nxt["type"] in NON_TOUCH_TYPES:
                j += 1
                continue
            if nxt.get("player_id") != pid or nxt.get("team_id") != e["team_id"]:
                break  # possession left this player before they acted again
            next_own = nxt
            break

        if next_own is None:
            acc.add(pid, "pr_lost_immediately")
            continue

        if next_own["type"] == "Pass":
            qm = q.qmap(next_own["qualifiers"])
            completed = next_own["outcome_type"] == "Successful"
            acc.add(pid, "pr_pass_attempts")
            if completed:
                acc.add(pid, "pr_pass_completed")
                x, y = cur.get("x"), cur.get("y")
                ex, ey = next_own.get("end_x"), next_own.get("end_y")
                if None not in (x, y, ex, ey):
                    if not q.has_qualifier(qm, q.CROSS_Q) and g.is_progressive_action((x, y), (ex, ey)):
                        acc.add(pid, "pr_prog_passes_off_recovery")
                    if ex < x - 2:
                        acc.add(pid, "pr_backward_passes")
        else:
            # a non-pass next action (carry-in-progress captured by movement to
            # a later position) — check if it represents meaningful ball progress
            x, y = cur.get("x"), cur.get("y")
            nx, ny = next_own.get("x"), next_own.get("y")
            if None not in (x, y, nx, ny) and g.is_progressive_action((x, y), (nx, ny)):
                chain_had_carry = True
                acc.add(pid, "pr_prog_carries_off_recovery")

        if chain_had_carry:
            # look one step further for a progressive pass completing the chain
            k = j + 1
            while k < len(events) and events[k]["type"] in NON_TOUCH_TYPES:
                k += 1
            if k < len(events):
                third = events[k]
                if third.get("player_id") == pid and third["type"] == "Pass" and third["outcome_type"] == "Successful":
                    qm3 = q.qmap(third["qualifiers"])
                    x2, y2 = next_own.get("x"), next_own.get("y")
                    ex2, ey2 = third.get("end_x"), third.get("end_y")
                    if None not in (x2, y2, ex2, ey2) and not q.has_qualifier(qm3, q.CROSS_Q) \
                            and g.is_progressive_action((x2, y2), (ex2, ey2)):
                        acc.add(pid, "pr_carry_then_progress")

    return acc.to_dict()


def finalize_post_recovery(totals: dict) -> dict:
    out = {}
    for pid, t in totals.items():
        recoveries = t.get("pr_recoveries", 0)
        pass_att = t.get("pr_pass_attempts", 0)
        pass_comp = t.get("pr_pass_completed", 0)
        out[pid] = {
            "pr_recoveries": recoveries,
            "pr_retention_pct": round(100 * pass_comp / pass_att, 1) if pass_att >= 10 else None,
            "pr_prog_pass_pct": round(100 * t.get("pr_prog_passes_off_recovery", 0) / recoveries, 1) if recoveries >= 10 else None,
            "pr_prog_carry_pct": round(100 * t.get("pr_prog_carries_off_recovery", 0) / recoveries, 1) if recoveries >= 10 else None,
            "pr_carry_then_progress_pct": round(100 * t.get("pr_carry_then_progress", 0) / recoveries, 1) if recoveries >= 10 else None,
            "pr_prog_passes_off_recovery": t.get("pr_prog_passes_off_recovery", 0),
            "pr_prog_carries_off_recovery": t.get("pr_prog_carries_off_recovery", 0),
            "pr_backward_release_pct": round(100 * t.get("pr_backward_passes", 0) / pass_comp, 1) if pass_comp >= 10 else None,
        }
    return out
