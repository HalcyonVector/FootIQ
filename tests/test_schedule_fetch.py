"""Schedule fetching in the weekly scrape: which failures are retried, which are not."""
import pytest

sw = pytest.importorskip("scraping.scrape_whoscored")


class _Reader:
    """Stands in for soccerdata.WhoScored: fails with the queued exceptions, then succeeds."""
    made = 0

    def __init__(self, errors, **kw):
        type(self).made += 1
        self.errors = errors
        self._driver = type("D", (), {"quit": lambda self: None})()

    def read_schedule(self):
        if self.errors:
            raise self.errors.pop(0)
        return "SCHEDULE"


@pytest.fixture
def fake(monkeypatch):
    import soccerdata
    monkeypatch.setattr(sw.time, "sleep", lambda s: None)
    monkeypatch.setattr(sw, "log", lambda m: None)
    _Reader.made = 0
    def install(errors):
        shared = list(errors)
        monkeypatch.setattr(soccerdata, "WhoScored", lambda **kw: _Reader(shared, **kw))
    return install


def test_error_kinds():
    missing_season = KeyError("None of [MultiIndex([('EUR-Champions League', '2627')])] are in the [index]")
    assert sw.schedule_error_kind(missing_season) == "not_published"
    assert sw.schedule_error_kind(ValueError("Expecting value")) == "transient"
    assert sw.schedule_error_kind(IndexError("list index out of range")) == "transient"


def test_unpublished_season_is_skipped_without_retrying(fake):
    fake([KeyError("None of [x] are in the [index]")])
    assert sw._fetch_schedule("EUR-Champions League", "2026-27", True) == (None, "not_published")
    assert _Reader.made == 1


def test_transient_errors_are_retried_with_a_fresh_browser(fake):
    fake([ValueError("block page"), IndexError("no Fixtures link"), ValueError("again")])
    assert sw._fetch_schedule("ESP-La Liga", "2026-27", True) == ("SCHEDULE", "ok")
    assert _Reader.made >= 2        # a new Chrome was started after the 2nd failure


def test_gives_up_after_five_attempts(fake):
    fake([ValueError("block page")] * 10)
    assert sw._fetch_schedule("GER-Bundesliga", "2026-27", True) == (None, "schedule_failed")
