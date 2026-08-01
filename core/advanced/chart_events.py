"""
Per-match extraction of lightweight per-event records for chart rendering —
raw coordinates/outcomes that the scalar category compute_*() functions
throw away after tallying counts. Collected in the SAME per-match loop as
Wave 1-4's aggregation (core/advanced/aggregator.py), merged into
data/advanced/chart_events/<category>/ (Hive-partitioned by league/season) —
separate from the main scalar table so /api/advanced-stats stays fast, and
partitioned so a single chart request reads one small slice, not every
player's every event.

Each extract_<category>(...) mirrors that category's own compute_<category>()
test logic (open-play filter, progressive test, zone test, etc.) so a chart's
dots/lines are consistent with its stat card's numbers. A few functions
duplicate a short walk already done elsewhere (carrying's carry-derivation,
hold-up's episode walk) rather than change derive_carries()/compute_holdup()'s
return shape — those are validated, working Wave 1-4 code and adding an
index-lookahead to their output risks a regression for very little gain.

Decision Making and Final Third need no extraction here — their charts are
built straight from the already-computed per-player-season row/cohort.
"""

from core.advanced import geometry as g, qualifiers as q, timing
from core.advanced.carries import NON_TOUCH_TYPES, MAX_CARRY_SECONDS, MIN_CARRY_DISTANCE_UNITS
from core.advanced.categories.shooting import SHOT_TYPES, ON_TARGET_TYPES
from core.advanced.categories.holdup import (
    MIN_HOLD_SECONDS, MAX_HOLD_SECONDS, DANGEROUS_WINDOW_SECONDS,
    OPPONENT_SHOT_TYPES, zone_of, _find_hold, _is_dangerous_aftermath,
)
from core.advanced.possession_chains import trace_forward_by_time


def extract_passing(events: list[dict]) -> dict:
    """Every open-play pass with coordinates: {x,y,end_x,end_y,completed,progressive,into_box,release_s}."""
    out: dict = {}
    release_times = timing.release_times_by_player(events)
    for e in events:
        if e["type"] != "Pass":
            continue
        pid = e["player_id"]
        if pid is None:
            continue
        qm = q.qmap(e["qualifiers"])
        if not q.is_open_play(qm):
            continue
        x, y, ex, ey = e.get("x"), e.get("y"), e.get("end_x"), e.get("end_y")
        if None in (x, y, ex, ey):
            continue
        completed = e["outcome_type"] == "Successful"
        is_cross = q.has_qualifier(qm, q.CROSS_Q)
        # Gated on completed to match finalize_passing's pass_prog_count (which
        # only counts COMPLETED progressive passes, not attempts) — an
        # unsuccessful progressive attempt falls through to plain "unsuccessful".
        progressive = completed and (not is_cross) and g.is_progressive_action((x, y), (ex, ey))
        into_box = completed and g.in_box(ex, ey)
        out.setdefault(pid, []).append({
            "x": x, "y": y, "end_x": ex, "end_y": ey,
            "completed": bool(completed), "progressive": bool(progressive), "into_box": bool(into_box),
            "release_s": release_times.get(e["event_id"]),
        })
    return out


def extract_takeons(events: list[dict]) -> dict:
    """Every standalone take-on attempt: {x,y,outcome(won/lost)} — separate
    from extract_carrying's "followup", which only captures a take-on when it
    immediately follows a carry, not every TakeOn event on its own."""
    out: dict = {}
    for e in events:
        if e["type"] != "TakeOn":
            continue
        pid = e["player_id"]
        if pid is None:
            continue
        x, y = e.get("x"), e.get("y")
        if x is None or y is None:
            continue
        out.setdefault(pid, []).append({
            "x": x, "y": y, "outcome": "won" if e["outcome_type"] == "Successful" else "lost",
        })
    return out


def extract_shooting(events: list[dict]) -> dict:
    """Every open-play shot: {x,y,outcome(goal/on_target/off_target),body_part}."""
    out: dict = {}
    for e in events:
        if e["type"] not in SHOT_TYPES:
            continue
        pid = e["player_id"]
        if pid is None:
            continue
        qm = q.qmap(e["qualifiers"])
        if q.has_qualifier(qm, q.OWN_GOAL_Q) or not q.is_open_play(qm):
            continue
        x, y = e.get("x"), e.get("y")
        if x is None or y is None:
            continue
        if e["type"] == "Goal":
            outcome = "goal"
        elif e["type"] in ON_TARGET_TYPES:
            outcome = "on_target"
        else:
            outcome = "off_target"
        out.setdefault(pid, []).append({"x": x, "y": y, "outcome": outcome, "body_part": q.body_part(qm) or ""})
    return out


def extract_carrying(events: list[dict]) -> dict:
    """Every carry (same 20s/2-unit rule as carries.derive_carries) plus what the
    player did immediately after: {start_x,start_y,end_x,end_y,progressive,followup}."""
    out: dict = {}
    prev = None
    for i, e in enumerate(events):
        if e["type"] in NON_TOUCH_TYPES:
            continue
        if e.get("player_id") is None or e.get("x") is None or e.get("y") is None:
            prev = None
            continue
        if prev is not None and prev["player_id"] == e["player_id"] and prev["team_id"] == e["team_id"] \
                and prev["period"] == e["period"]:
            dt = timing.event_seconds(e) - timing.event_seconds(prev)
            if 0 <= dt <= MAX_CARRY_SECONDS:
                straight = ((e["x"] - prev["x"]) ** 2 + (e["y"] - prev["y"]) ** 2) ** 0.5
                if straight >= MIN_CARRY_DISTANCE_UNITS:
                    pid = e["player_id"]
                    start, end = (prev["x"], prev["y"]), (e["x"], e["y"])
                    progressive = g.is_progressive_action(start, end)
                    followup = "none"
                    nxt = events[i + 1] if i + 1 < len(events) else None
                    if nxt and nxt.get("player_id") == pid and nxt.get("team_id") == e["team_id"]:
                        if nxt["type"] == "Pass" and nxt["outcome_type"] == "Successful":
                            nqm = q.qmap(nxt["qualifiers"])
                            nx, ny, nex, ney = nxt.get("x"), nxt.get("y"), nxt.get("end_x"), nxt.get("end_y")
                            if not q.has_qualifier(nqm, q.CROSS_Q) and None not in (nx, ny, nex, ney) \
                                    and g.is_progressive_action((nx, ny), (nex, ney)):
                                followup = "prog_pass"
                        elif nxt["type"] == "TakeOn":
                            followup = "takeon_won" if nxt["outcome_type"] == "Successful" else "takeon_lost"
                    out.setdefault(pid, []).append({
                        "start_x": start[0], "start_y": start[1], "end_x": end[0], "end_y": end[1],
                        "progressive": bool(progressive), "followup": followup,
                    })
        prev = e
    return out


def extract_aerial(events: list[dict]) -> dict:
    """Every aerial duel: {x,y,won,phase(open_play/set_piece)}."""
    out: dict = {}
    for e in events:
        if e["type"] != "Aerial":
            continue
        pid = e["player_id"]
        if pid is None:
            continue
        x, y = e.get("x"), e.get("y")
        if x is None or y is None:
            continue
        qm = q.qmap(e["qualifiers"])
        phase = "open_play" if q.is_open_play(qm) else "set_piece"
        out.setdefault(pid, []).append({"x": x, "y": y, "won": e["outcome_type"] == "Successful", "phase": phase})
    return out


def extract_holdup(events: list[dict]) -> dict:
    """One record per hold-up episode: {x,y,zone(final/middle/defensive),
    outcome(retained/prog_release/shot_from_hold/dangerous_loss/lost)}.
    Mirrors compute_holdup's delivery-to-release model exactly (see that
    module's docstring): duration is measured from the delivering event
    (usually a teammate's pass) to the receiving player's last adjacent
    touch, not from the player's own first touch to their own last touch."""
    out: dict = {}
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

        lost = last["type"] == "Dispossessed" or (last["type"] == "Pass" and last["outcome_type"] == "Unsuccessful")
        outcome = "retained"
        if last["type"] == "Pass" and last["outcome_type"] == "Successful":
            ex, ey = last.get("end_x"), last.get("end_y")
            qm = q.qmap(last["qualifiers"])
            if None not in (ex, ey) and not q.has_qualifier(qm, q.CROSS_Q) \
                    and g.is_progressive_action((x0, y0), (ex, ey)):
                outcome = "prog_release"
        elif last["type"] in OPPONENT_SHOT_TYPES:
            outcome = "shot_from_hold"
        elif lost:
            aftermath = trace_forward_by_time(events, last_idx, window_seconds=DANGEROUS_WINDOW_SECONDS)
            outcome = "dangerous_loss" if _is_dangerous_aftermath(aftermath, team_id) else "lost"

        out.setdefault(pid, []).append({"x": x0, "y": y0, "zone": zone_of(x0), "outcome": outcome})
    return out


def _in_half_space(x, y) -> bool:
    return x is not None and y is not None and x >= 50 and g.half_space_of(x, y) is not None


def extract_half_spaces(events: list[dict], carries: list[dict]) -> tuple[dict, dict]:
    """Returns (offense, defense) dicts. offense: {x,y,end_x,end_y,kind(prog_pass/
    pass/unsuccessful/prog_carry/carry)}. defense: {x,y,kind(tackle/interception/
    recovery/block/aerial)} — both restricted to the two half-space strips."""
    offense: dict = {}
    defense: dict = {}
    for e in events:
        pid = e["player_id"]
        if pid is None:
            continue
        etype = e["type"]
        x, y = e.get("x"), e.get("y")

        if etype == "Pass":
            qm = q.qmap(e["qualifiers"])
            if not q.is_open_play(qm) or not _in_half_space(x, y):
                continue
            completed = e["outcome_type"] == "Successful"
            ex, ey = e.get("end_x"), e.get("end_y")
            if ex is None or ey is None:
                continue
            progressive = completed and not q.has_qualifier(qm, q.CROSS_Q) and g.is_progressive_action((x, y), (ex, ey))
            kind = "prog_pass" if progressive else ("pass" if completed else "unsuccessful")
            offense.setdefault(pid, []).append({"x": x, "y": y, "end_x": ex, "end_y": ey, "kind": kind})
        elif etype == "Tackle" and _in_half_space(x, y):
            defense.setdefault(pid, []).append({"x": x, "y": y, "kind": "tackle"})
        elif etype == "Interception" and _in_half_space(x, y):
            defense.setdefault(pid, []).append({"x": x, "y": y, "kind": "interception"})
        elif etype == "BallRecovery" and _in_half_space(x, y):
            defense.setdefault(pid, []).append({"x": x, "y": y, "kind": "recovery"})
        elif etype == "BlockedPass" and _in_half_space(x, y):
            defense.setdefault(pid, []).append({"x": x, "y": y, "kind": "block"})
        elif etype == "Aerial" and _in_half_space(x, y) and e["outcome_type"] == "Successful":
            defense.setdefault(pid, []).append({"x": x, "y": y, "kind": "aerial"})

    for c in carries:
        if not _in_half_space(c["start_x"], c["start_y"]):
            continue
        progressive = g.is_progressive_action((c["start_x"], c["start_y"]), (c["end_x"], c["end_y"]))
        offense.setdefault(c["player_id"], []).append({
            "x": c["start_x"], "y": c["start_y"], "end_x": c["end_x"], "end_y": c["end_y"],
            "kind": "prog_carry" if progressive else "carry",
        })
    return offense, defense


def extract_tempo(events: list[dict], carries: list[dict]) -> dict:
    """Injector/reset passes+carries: {x,y,end_x,end_y,kind(injector_pass/reset_pass/injector_carry),release_s}."""
    out: dict = {}
    release_times = timing.release_times_by_player(events)
    for e in events:
        if e["type"] != "Pass":
            continue
        pid = e["player_id"]
        if pid is None:
            continue
        qm = q.qmap(e["qualifiers"])
        if not q.is_open_play(qm):
            continue
        x, y, ex, ey = e.get("x"), e.get("y"), e.get("end_x"), e.get("end_y")
        if None in (x, y, ex, ey):
            continue
        rel = release_times.get(e["event_id"])
        is_forward = ex > x
        is_progressive = not q.has_qualifier(qm, q.CROSS_Q) and g.is_progressive_action((x, y), (ex, ey))
        if rel is not None and rel < 2.0 and is_forward and is_progressive:
            kind = "injector_pass"
        elif ex < x - 5 or (rel is not None and rel > 4.0):
            kind = "reset_pass"
        else:
            continue
        out.setdefault(pid, []).append({"x": x, "y": y, "end_x": ex, "end_y": ey, "kind": kind, "release_s": rel})

    for c in carries:
        start, end = (c["start_x"], c["start_y"]), (c["end_x"], c["end_y"])
        if c["duration_s"] < 3.0 and g.is_progressive_action(start, end):
            out.setdefault(c["player_id"], []).append({
                "x": start[0], "y": start[1], "end_x": end[0], "end_y": end[1], "kind": "injector_carry",
            })
    return out


def extract_defending(events: list[dict]) -> dict:
    """Every defensive action: {x,y,action(tackle/interception/block/clearance/recovery/aerial),outcome(won/lost)}."""
    out: dict = {}
    for e in events:
        pid = e.get("player_id")
        if pid is None:
            continue
        etype = e["type"]
        x, y = e.get("x"), e.get("y")
        if x is None or y is None:
            continue
        if etype == "Tackle":
            out.setdefault(pid, []).append({"x": x, "y": y, "action": "tackle",
                                             "outcome": "won" if e["outcome_type"] == "Successful" else "lost"})
        elif etype == "Interception":
            out.setdefault(pid, []).append({"x": x, "y": y, "action": "interception", "outcome": "won"})
        elif etype == "BlockedPass":
            out.setdefault(pid, []).append({"x": x, "y": y, "action": "block", "outcome": "won"})
        elif etype == "Clearance":
            out.setdefault(pid, []).append({"x": x, "y": y, "action": "clearance", "outcome": "won"})
        elif etype == "BallRecovery":
            out.setdefault(pid, []).append({"x": x, "y": y, "action": "recovery", "outcome": "won"})
        elif etype == "Aerial":
            out.setdefault(pid, []).append({"x": x, "y": y, "action": "aerial",
                                             "outcome": "won" if e["outcome_type"] == "Successful" else "lost"})
    return out


def extract_post_recovery(events: list[dict]) -> dict:
    """One record per recovery: {x,y,end_x,end_y,outcome(prog_pass/pass/prog_carry/unsuccessful)} —
    same shape as Combination Play's receptions so visuals/linkup.py's plotting style can be reused."""
    out: dict = {}
    for i, e in enumerate(events):
        if e["type"] != "BallRecovery":
            continue
        pid = e["player_id"]
        if pid is None or e.get("x") is None or e.get("y") is None:
            continue
        x, y = e["x"], e["y"]

        next_own = None
        j = i + 1
        while j < len(events):
            nxt = events[j]
            if nxt["type"] in NON_TOUCH_TYPES:
                j += 1
                continue
            if nxt.get("player_id") != pid or nxt.get("team_id") != e["team_id"]:
                break
            next_own = nxt
            break

        if next_own is None:
            out.setdefault(pid, []).append({"x": x, "y": y, "end_x": None, "end_y": None, "outcome": "unsuccessful"})
            continue

        if next_own["type"] == "Pass":
            completed = next_own["outcome_type"] == "Successful"
            ex, ey = next_own.get("end_x"), next_own.get("end_y")
            outcome = "unsuccessful"
            if completed and ex is not None and ey is not None:
                qm = q.qmap(next_own["qualifiers"])
                if not q.has_qualifier(qm, q.CROSS_Q) and g.is_progressive_action((x, y), (ex, ey)):
                    outcome = "prog_pass"
                else:
                    outcome = "pass"
            out.setdefault(pid, []).append({"x": x, "y": y, "end_x": ex, "end_y": ey, "outcome": outcome})
        else:
            nx, ny = next_own.get("x"), next_own.get("y")
            outcome = "prog_carry" if (nx is not None and ny is not None
                                        and g.is_progressive_action((x, y), (nx, ny))) else "unsuccessful"
            out.setdefault(pid, []).append({"x": x, "y": y, "end_x": nx, "end_y": ny, "outcome": outcome})
    return out


def extract_goalkeeping(events: list[dict], rosters: list[dict], minutes: dict) -> dict:
    """Every shot faced by a keeper: {x,y,outcome(saved/conceded)}. Attribution
    mirrors compute_goalkeeping's own-team/opponent lookup; goals split between
    co-keepers there are simplified here to the keeper with the most minutes."""
    out: dict = {}
    gk_team_of = {r["player_id"]: r["team_id"] for r in rosters if r["position"] == "GK"}
    gks_by_team: dict = {}
    for pid, team_id in gk_team_of.items():
        mins = minutes.get(pid, 0)
        if mins > 0:
            gks_by_team.setdefault(team_id, []).append((pid, mins))

    team_ids = list({r["team_id"] for r in rosters if r["team_id"] is not None})
    opponent_of = {}
    if len(team_ids) == 2:
        opponent_of = {team_ids[0]: team_ids[1], team_ids[1]: team_ids[0]}

    for e in events:
        etype = e["type"]
        pid = e["player_id"]
        x, y = e.get("x"), e.get("y")
        if x is None or y is None:
            continue
        if etype == "Save" and pid in gk_team_of:
            out.setdefault(pid, []).append({"x": x, "y": y, "outcome": "saved"})
        elif etype == "Goal" and not q.has_qualifier(q.qmap(e["qualifiers"]), q.OWN_GOAL_Q):
            keepers = gks_by_team.get(opponent_of.get(e.get("team_id")), [])
            if keepers:
                gk_pid = max(keepers, key=lambda kv: kv[1])[0]
                # Goal events carry the SHOOTER's attacking-direction-normalized
                # x,y (near x=100, the opponent's goal) while Save events carry
                # the KEEPER's own (near x=0) — flip so every shot faced lands
                # in the same frame, near the keeper's own goal.
                out.setdefault(gk_pid, []).append({"x": 100 - x, "y": 100 - y, "outcome": "conceded"})
    return out
