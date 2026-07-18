"""
Shared per-match accumulator used by every category module. Keys prefixed
"list__" hold python lists that get CONCATENATED across matches by the
aggregator (for medians etc.); every other key is a number that gets SUMMED
across matches. This lets aggregator.py merge any category's output the
same generic way without category-specific merge logic.
"""

from collections import defaultdict


class PlayerAcc:
    """{player_id: {metric_key: value}} with convenient +=/list-append helpers."""

    def __init__(self):
        self._data: dict = defaultdict(lambda: defaultdict(float))
        self._lists: dict = defaultdict(lambda: defaultdict(list))

    def add(self, player_id, key: str, amount: float = 1.0):
        if player_id is None:
            return
        self._data[player_id][key] += amount

    def append(self, player_id, key: str, value):
        if player_id is None:
            return
        self._lists[player_id][f"list__{key}"].append(value)

    def to_dict(self) -> dict:
        out = {}
        for pid, d in self._data.items():
            out.setdefault(pid, {}).update(d)
        for pid, d in self._lists.items():
            out.setdefault(pid, {}).update(d)
        return out


def merge_into(totals: dict, match_result: dict) -> None:
    """Merge one match's {player_id: {key: value|list}} into a running
    per-season totals dict of the same shape, in place."""
    for pid, fields in match_result.items():
        bucket = totals.setdefault(pid, {})
        for key, val in fields.items():
            if key.startswith("list__"):
                bucket.setdefault(key, []).extend(val)
            else:
                bucket[key] = bucket.get(key, 0.0) + val
