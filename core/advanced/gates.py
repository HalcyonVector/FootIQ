"""
Minimum-sample gates that follow how much of a season has been played.

Many ratio metrics (aerial win rate, take-on success, pass accuracy...) are only
reported once a player has enough attempts (">= 10 duels", ">= 15 take-ons"...).
Those counts were chosen for a full season; applied unchanged to a season that is
a quarter played they hide most of a regular starter's profile behind "-".

The aggregator calls set_scale(progress) while it finalises one league-season
(progress = share of the season's games played, 1.0 once it is finished), and the
category modules write their gates as gates.gate(10) instead of a bare 10.
For a finished season gate(n) == n, so completed seasons are unchanged.
"""
import math

_SCALE = 1.0
_FLOOR = 3          # never ask for fewer than this many attempts (or n itself, if smaller)
NO_ROUND_ROBIN = {"Champions League", "Europa League", "World Cup", "European Championship"}
FINISHED_AT = 0.9   # a season this far along is treated as finished (a few cached matches may be missing)


def set_scale(scale: float) -> None:
    global _SCALE
    _SCALE = max(0.0, min(1.0, float(scale)))


def gate(n: int) -> int:
    if _SCALE >= 1.0:
        return n
    return max(min(n, _FLOOR), math.ceil(n * _SCALE))


def season_progress(league: str, n_matches: int, n_teams: int) -> float:
    """Share of a double round-robin season played so far (1.0 = finished or not applicable)."""
    if league in NO_ROUND_ROBIN or n_teams < 8 or n_matches <= 0:
        return 1.0
    per_team = 2 * n_matches / n_teams
    p = per_team / (2 * (n_teams - 1))
    return 1.0 if p >= FINISHED_AT else round(p, 4)
