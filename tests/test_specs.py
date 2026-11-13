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


def _pass_row(box=False, prog=False, ok=True):
    return {"into_box": box, "progressive": prog, "completed": ok, "x": 50, "y": 50, "end_x": 70, "end_y": 50, "release_s": 1.0}


def test_pass_tiles_for_the_progressive_subset_say_so_and_have_no_empty_rows():
    """The default Passing view feeds the tiles only the progressive and into-box passes. They must
    say it is a subset of the full count and split each kind by how it ended, not show an empty
    Completed / Unsuccessful pair next to a total that looks like the player's whole season."""
    subset = [_pass_row(box=True), _pass_row(box=True, ok=False), _pass_row(prog=True), _pass_row(prog=True), _pass_row(prog=True, ok=False)]
    out = sp.pass_outcomes(subset, of=477)
    assert "5 progressive and into-box passes" in out["sub"] and "477" in out["sub"]
    counts = {i["label"]: i["text"].split()[0] for i in out["items"]}
    assert counts == {"Into box, completed": "1", "Into box, missed": "1", "Progressive, completed": "2", "Progressive, missed": "1"}
    assert "477" in sp.pass_zones(subset, of=477)["sub"]
    # the whole-season view is unchanged apart from its wording
    assert sp.pass_outcomes(subset)["sub"] == "All 5 passes"


def _cat(key, percentiles):
    return {"key": key, "label": key, "rows": [{"stats": [{"percentile": p, "no_data": False} for p in percentiles]}]}


def test_profile_radar_averages_each_category_and_skips_empty_ones():
    cats = [_cat("passing", [80, 60]), _cat("shooting", [50]), _cat("carrying", [90]),
            {"key": "tempo", "label": "Tempo", "rows": [{"stats": [{"percentile": 0, "no_data": True}]}]},   # nothing usable
            _cat("linkup", [70])]                                                                              # pairwise, not a category
    spec = sp.profile_radar(cats, "A. Player")
    assert spec["axes"] == ["Passing", "Shooting", "Carrying"]
    assert spec["series"][0]["values"] == [70.0, 50.0, 90.0] and spec["series"][0]["name"] == "A. Player"
    assert sp.profile_radar(cats[:2], "x") is None          # fewer than three axes is not a shape


def test_metric_scatter_is_compact_and_nan_safe():
    pts = [{"x": 1.23456, "y": float("nan"), "name": "A", "team": "T", "league": "L", "season": "2025-26", "group": "midfielder", "id": 1, "minutes": 900}]
    spec = sp.metric_scatter(pts, "X", "Y", "%", "", x_invert=True)
    assert spec["type"] == "xy" and spec["xinvert"] and not spec["yinvert"]
    assert spec["points"][0][:3] == [1.235, None, "A"]       # NaN becomes null, not an invalid JSON token
