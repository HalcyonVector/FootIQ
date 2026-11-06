"""Chart specs (visuals/specs.py) — plain data, so they can be checked without a browser."""
import json

from visuals import specs as sp


def _pass(x, y, ex, ey, completed=True, prog=False, box=False, rel=1.0):
    return {"x": x, "y": y, "end_x": ex, "end_y": ey, "completed": completed,
            "progressive": prog, "into_box": box, "release_s": rel}


def test_passing_map_buckets_and_mode_filter():
    passes = [_pass(30, 40, 60, 50, prog=True), _pass(70, 40, 90, 50, prog=True, box=True),
              _pass(20, 40, 25, 50), _pass(20, 40, 25, 50, completed=False), _pass(None, 40, 25, 50)]
    prog_only = {L["id"]: L for L in sp.passing_map(passes, "progressive")["layers"]}
    assert prog_only["box"]["count"] == 1 and prog_only["prog"]["count"] == 1
    assert prog_only["ok"]["pts"] == [] and prog_only["ok"]["count"] == 1      # counted for the legend, not drawn
    everything = {L["id"]: L for L in sp.passing_map(passes, "all")["layers"]}
    assert len(everything["ok"]["pts"]) == 1 and len(everything["bad"]["pts"]) == 1   # incomplete pass with coords is drawn
    assert sum(L["count"] for L in everything.values()) == 4                   # the coordinate-less pass is ignored


def test_count_bars_percentages():
    spec = sp.count_bars([("A", 3, "#fff"), ("B", 1, "#000")])
    assert [i["text"] for i in spec["items"]] == ["3 (75%)", "1 (25%)"]
    assert spec["items"][0]["value"] == 75.0
    assert sp.count_bars([("A", 0, "#fff")])["items"][0]["text"] == "0 (0%)"      # empty -> no division by zero


def test_hist_edges_and_marker():
    h = sp.hist([1, 2, 2, 3, 9], 4, "m", marker=(5, "me"))
    assert sum(h["counts"]) == 5 and len(h["edges"]) == len(h["counts"]) + 1
    assert h["median"] == 2 and h["marker"] == {"value": 5.0, "label": "me"}
    assert sp.hist([], 4)["counts"] == []


def test_nan_never_reaches_json():
    nan = float("nan")
    spec = sp.passing_map([_pass(nan, 40, 60, 50, prog=True), _pass(30, 40, 60, 50, prog=True)], "all")
    assert "NaN" not in json.dumps(spec)
    assert sum(L["count"] for L in spec["layers"]) == 1


def test_carry_rose_direction():
    forward = [{"progressive": True, "start_x": 30, "start_y": 30, "end_x": 60, "end_y": 30}]
    spec, stats = sp.carry_rose(forward)
    assert abs(spec["angle"]) < 0.01                       # pointing straight forward (east)
    assert sp.carry_rose([])[0]["angle"] is None


def test_carry_map_followup_layers_respect_show():
    carries = [{"progressive": True, "start_x": 30, "start_y": 30, "end_x": 60, "end_y": 30, "followup": "takeon_won"}]
    spec, stats = sp.carry_map(carries, show=("prog_pass",))
    layers = {L["id"]: L for L in spec["layers"]}
    assert layers["tw"]["pts"] == [] and layers["tw"]["count"] == 1 and stats["takeon_won_after"] == 1


def test_trend_keeps_gaps():
    t = sp.trend(["a", "b", "c"], [10, None, 30.04])
    assert t["values"] == [10.0, None, 30.0]


def test_half_space_map_modes():
    off = [{"x": 70, "y": 30, "end_x": 80, "end_y": 30, "kind": "prog_pass"}]
    dfn = [{"x": 70, "y": 30, "kind": "tackle"}]
    assert {L["id"] for L in sp.half_space_map(off, dfn, "offensive")["layers"]} == set(sp.HS_OFF)
    assert {L["id"] for L in sp.half_space_map(off, dfn, "both")["layers"]} == set(sp.HS_OFF) | {"tackle"}   # empty defensive kinds are hidden in "both"
    assert len(sp.half_space_map(off, dfn, "both")["guides"]) == 2


def test_percentile_color_matches_endpoints():
    assert sp.percentile_color(0) == "#ef4444" and sp.percentile_color(100) == "#3b82f6"
