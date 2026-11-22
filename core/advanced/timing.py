"""
Timestamp helpers. expanded_minute is the continuous, stoppage-time-aware
match clock (unlike minute/period which can behave oddly around halftime),
so it's the right basis for release-time / tempo calculations.
"""
import math

MAX_RELEASE_GAP_SECONDS = 20.0  # beyond this, treat as a "fresh" possession, not a release
BALL_SPEED_M_S = 13.0           # a typical pass or clearance: how long the ball is in the air before it arrives

# The passer's own events that hand them the ball: the release is timed from here.
_WON_BALL = {"BallRecovery", "Interception", "KeeperPickup", "Claim", "Smother"}
_WON_IF_SUCCESSFUL = {"Tackle", "Aerial", "TakeOn"}   # a won tackle or header gains the ball; a take-on keeps it
# The passer's own events while already on the ball: keep looking further back for when they got it.
_ON_BALL = {"BallTouch", "TakeOn", "Dispossessed", "Foul", "Card", "Challenge"}
# Events that never mean someone touched the ball.
_NO_BALL = {"Start", "End", "FormationChange", "FormationSet", "SubstitutionOff", "SubstitutionOn",
            "Card", "OffsideProvoked", "CornerAwarded", "PenaltyFaced", "ShieldBallOpp", "Error"}


def event_seconds(e: dict) -> float:
    em = e.get("expanded_minute")
    if em is None:
        em = e.get("minute") or 0
    return float(em) * 60.0 + float(e.get("second") or 0)


def _travel_seconds(e: dict) -> float:
    """How long a pass or clearance takes to arrive, from its length (Opta's 0-100 pitch is 105 x 68 m)."""
    if e.get("x") is None or e.get("end_x") is None or e.get("end_y") is None or e.get("y") is None:
        return 0.0
    dx = (e["end_x"] - e["x"]) * 1.05
    dy = (e["end_y"] - e["y"]) * 0.68
    return math.hypot(dx, dy) / BALL_SPEED_M_S


def _is_set_piece(e: dict) -> bool:
    from core.advanced import qualifiers as q
    return not q.is_open_play(q.qmap(e.get("qualifiers") or []))


def reception_seconds(events: list[dict], i: int):
    """When did the player making the pass at index i get the ball? The feed has no "ball received"
    event, so walk back from the pass: a teammate's completed pass (plus the time the ball travels)
    or any other teammate touch delivered it; one of the passer's own ball-winning events (recovery,
    interception, won tackle or header) won it; an opponent's clearance or loose touch left it there.
    The passer's own dribbles and touches in between are skipped (they already had it), and so are
    the opponent's records of duels they lost. None when nothing plausible is found within
    MAX_RELEASE_GAP_SECONDS, across a period break, or when an earlier pass by the same player shows
    they gave the ball away and the moment they got it back is not in the feed."""
    p = events[i]
    pid, team, period = p.get("player_id"), p.get("team_id"), p.get("period")
    t = event_seconds(p)
    for j in range(i - 1, -1, -1):
        e = events[j]
        tj = event_seconds(e)
        if t - tj > MAX_RELEASE_GAP_SECONDS or e.get("period") != period:
            return None
        typ = e.get("type")
        if typ in _NO_BALL or e.get("player_id") is None:
            continue
        won = e.get("outcome_type") == "Successful"
        if e.get("player_id") == pid:
            if typ in _WON_BALL or (typ in _WON_IF_SUCCESSFUL and won and typ != "TakeOn"):
                return tj
            if typ in _ON_BALL:
                continue
            return None            # e.g. their own earlier pass: where they got it back is not recorded
        if e.get("team_id") == team:
            if typ == "Pass":
                return tj + _travel_seconds(e) if won else None
            return tj              # a header, flick or touch by a teammate put it there
        # the opponent
        if typ in ("Aerial", "Challenge", "Tackle", "Foul") and not won:
            continue               # their record of a duel they lost, or a foul on the passer
        if typ in ("Pass", "Clearance"):
            return tj + _travel_seconds(e)
        return tj                  # a loose touch, a block, a save that fell to the passer


def release_times_by_player(events: list[dict]) -> dict:
    """{event_id: seconds} from the moment the passer got the ball (reception_seconds) to the pass,
    for open-play passes only (a corner or free kick is not a decision under pressure). Rounded to
    0.1 s; the feed's clock is in whole seconds, so any single value is good to about a second.

    This replaced timing from the passer's own previous event: the feed records no reception, so
    that timed only the 36 to 46% of passes with an earlier event by the same player close by, and
    mostly measured the gap between two of their actions (median 7 s), not time on the ball."""
    # Passing, tempo, decision making and the chart events each ask for the same match in turn:
    # work it out once per match (about 11 ms) instead of five times.
    if _LAST[0] is events and _LAST[1] == len(events):
        return _LAST[2]
    release: dict = {}
    for i, e in enumerate(events):
        if e.get("type") != "Pass" or e.get("player_id") is None or _is_set_piece(e):
            continue
        got = reception_seconds(events, i)
        if got is None:
            continue
        release[e["event_id"]] = round(max(0.0, event_seconds(e) - got), 1)
    _LAST[:] = [events, len(events), release]
    return release


_LAST: list = [None, 0, None]   # (events list, its length, its release times): the last match worked out
