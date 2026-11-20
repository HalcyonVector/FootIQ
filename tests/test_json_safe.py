"""Answers stay valid JSON even when a value is NaN or infinite (browsers reject a bare NaN)."""
import json

import app as flask_app
from core.advanced.categories.final_third import pillar_floor_scores, pillar_per_touch_scores


def _strict(text):
    def bad(x):
        raise ValueError(x)
    return json.loads(text, parse_constant=bad)


def test_nan_and_infinity_go_out_as_null_and_strings_are_untouched():
    with flask_app.app.app_context():
        text = flask_app.app.json.dumps({"a": float("nan"), "b": [1.0, float("inf"), float("-inf")],
                                         "note": "NaN, Infinity and a value", "c": 2})
    d = _strict(text)
    assert d == {"a": None, "b": [1.0, None, None], "note": "NaN, Infinity and a value", "c": 2}


def test_final_third_scores_treat_nan_as_missing():
    # a 1-minute player: no passes, so pass accuracy is NaN; the Link-Up score used to come out NaN
    row = {"ft_passes_p90": 0.0, "pass_accuracy_pct": float("nan"), "ft_key_passes_p90": float("nan"),
           "ft_touches_p90": float("nan")}
    floor = pillar_floor_scores(row)
    assert all(v == v for v in floor.values()) and floor["linkup"] == 0
    assert all(v == 0 for v in pillar_per_touch_scores(row).values())
