"""A request the client got wrong is a 400 with a short reason, never a 500 (which should only ever
mean a fault on the server), and a 500 never echoes raw Python error text."""
import pytest

import app as flask_app

CASES = [
    ("/api/advanced-stats", {}), ("/api/advanced-stats", {"player_id": "abc"}), ("/api/player-overview", {"player_id": "x"}),
    ("/api/pass-map", {}), ("/api/category-chart", {"player_id": 1}), ("/api/linkup-detail", {"passer_id": 1, "teammate_id": "x"}),
    ("/api/compare-stats", {"players": [{"player_id": "x"}, {"player_id": "y"}]}), ("/api/scout-similar", {"player_id": 1, "max_age": "old"}),
    ("/api/explore", {}), ("/api/explore", {"metric": "pass_prog_count_p90", "min_minutes": "lots"}), ("/api/explore-scatter", {}),
]


@pytest.mark.parametrize("url,body", CASES)
def test_bad_input_is_a_400(url, body):
    r = flask_app.app.test_client().post(url, json=body)
    assert r.status_code == 400, (url, body, r.status_code, r.get_data(as_text=True))
    assert "invalid literal" not in r.get_data(as_text=True)


def test_a_body_that_is_not_an_object_is_a_400():
    c = flask_app.app.test_client()
    assert c.post("/api/advanced-stats", data="notjson", content_type="application/json").status_code == 400
    assert c.post("/api/advanced-stats", json=[1, 2]).status_code == 400
