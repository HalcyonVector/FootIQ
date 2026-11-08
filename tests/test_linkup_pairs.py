"""get_linkup_pairs: the compact Arrow-backed replacement for the old pandas summary frame."""
import os

import pytest

from core.advanced import config, store

pytestmark = pytest.mark.skipif(not os.path.exists(config.LINKUP_SUMMARY_PARQUET), reason="no data on this machine")


def _any_pair():
    import pyarrow.parquet as pq
    t = pq.read_table(config.LINKUP_SUMMARY_PARQUET).slice(0, 1).to_pylist()[0]
    return t


def test_pairs_sorted_and_complete():
    p = _any_pair()
    rows = store.get_linkup_pairs(p["passer_id"], p["league"], p["season"])
    assert rows and all(r["passer_name"] == p["passer_name"] for r in rows)
    counts = [r["count"] for r in rows]
    assert counts == sorted(counts, reverse=True)
    assert any(r["receiver_id"] == p["receiver_id"] and r["count"] == p["count"] for r in rows)


def test_single_receiver_filter_and_unknown_player():
    p = _any_pair()
    one = store.get_linkup_pairs(p["passer_id"], p["league"], p["season"], receiver_id=p["receiver_id"])
    assert len(one) == 1 and one[0]["receiver_name"] == p["receiver_name"]
    assert store.get_linkup_pairs(-1, p["league"], p["season"]) == []
