"""
Shared possession-chain tracing, used by Aerial Duels (6-events-deep),
Hold-Up Play (10s time window), Decision Making (2-action chains), and
Post-Recovery (their own local variant lives in post_recovery.py since it
needs same-player adjacency rather than any-player forward tracing).
"""

from core.advanced import timing
from core.advanced.carries import NON_TOUCH_TYPES


def index_by_seq(events: list[dict]) -> dict:
    """seq_id -> event, for resolving RelatedEventId/OppositeRelatedEvent qualifiers
    (which reference the small per-match eventId counter, not the global event id)."""
    return {e["seq_id"]: e for e in events if e.get("seq_id") is not None}


def trace_forward(events: list[dict], start_idx: int, max_depth: int = 6) -> list[dict]:
    """Up to max_depth subsequent 'real' events (any player/team) after start_idx,
    skipping administrative event types."""
    out = []
    j = start_idx + 1
    while j < len(events) and len(out) < max_depth:
        e = events[j]
        if e["type"] not in NON_TOUCH_TYPES:
            out.append(e)
        j += 1
    return out


def trace_forward_by_time(events: list[dict], start_idx: int, window_seconds: float) -> list[dict]:
    """Subsequent 'real' events within window_seconds of start_idx's timestamp."""
    if start_idx >= len(events):
        return []
    t0 = timing.event_seconds(events[start_idx])
    out = []
    j = start_idx + 1
    while j < len(events):
        e = events[j]
        if timing.event_seconds(e) - t0 > window_seconds:
            break
        if e["type"] not in NON_TOUCH_TYPES:
            out.append(e)
        j += 1
    return out
