"""Every page renders (catches template mistakes before a deploy)."""
import pytest

import app as app_module

PAGES = {
    "/": "Elite Football Data Engine",
    "/player": 'id="main-search"',
    "/compare": "Compare",
    "/league": "League",
    "/team": 'id="tm-title"',
    "/scout": 'id="scout-season-pool"',
    "/explore": 'id="explore-quad"',
    "/coverage": 'id="cov-table"',
}


@pytest.fixture(scope="module")
def client(monkeypatch_module):
    monkeypatch_module.setattr(app_module, "_ensure_warm_started", lambda: None)   # pages need no data
    return app_module.app.test_client()


@pytest.fixture(scope="module")
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


@pytest.mark.parametrize("route,marker", PAGES.items())
def test_page_renders(client, route, marker):
    res = client.get(route)
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert marker in html
    assert "{{" not in html and "{%" not in html           # no unrendered template syntax
    assert "<footer" in html


def test_season_pickers_default_to_a_listed_season(client):
    html = client.get("/player").get_data(as_text=True)
    default = app_module._season_pickers()["default_season"]
    assert f'<option value="{default}" selected>' in html
