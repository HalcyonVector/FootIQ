"""The data health check must not treat unplayed fixtures of the current season as unusable."""
import pytest

pytest.importorskip("pandas")
from scraping import check_data_health as h


def _run(monkeypatch, files, current):
    """files: {season: [json value or Exception, ...]}"""
    monkeypatch.setattr(h, "iter_match_files", lambda league, season: [(season, i) for i in range(len(files.get(season, [])))])

    def load(fp):
        v = files[fp[0]][fp[1]]
        if isinstance(v, Exception):
            raise v
        return v
    monkeypatch.setattr(h, "load_match_json", load)
    return h.check_league_seasons(0.05, leagues=["Premier League"], seasons=list(files), current=current)


def test_unplayed_fixtures_are_pending_not_unusable(monkeypatch):
    res = _run(monkeypatch, {"2026-27": [{"a": 1}] * 9 + [None] * 91}, current="2026-27")
    r = res[0]
    assert (r["total"], r["pending"], r["bad"], r["flagged"]) == (9, 91, 0, False)


def test_unreadable_files_still_count_in_the_current_season(monkeypatch):
    res = _run(monkeypatch, {"2026-27": [{"a": 1}] * 8 + [ValueError("corrupt")] * 2 + [None] * 50}, current="2026-27")
    assert res[0]["bad"] == 2 and res[0]["flagged"]


def test_finished_season_nulls_are_real_gaps(monkeypatch):
    res = _run(monkeypatch, {"2025-26": [{"a": 1}] * 70 + [None] * 30}, current="2026-27")
    assert res[0]["bad"] == 30 and res[0]["flagged"]
