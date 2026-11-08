"""In-progress seasons relax the minimum-sample gates; finished seasons are untouched."""
import pandas as pd

from core.advanced import config, gates
from core.advanced.categories.aerial import finalize_aerial


def teardown_function():
    gates.set_scale(1.0)


def test_gate_unchanged_for_a_finished_season():
    gates.set_scale(1.0)
    assert [gates.gate(n) for n in (5, 10, 25)] == [5, 10, 25]


def test_gate_scales_down_but_keeps_a_floor():
    gates.set_scale(0.25)
    assert gates.gate(10) == 3 and gates.gate(25) == 7 and gates.gate(2) == 2   # never above the original, never below 3


def test_season_progress():
    assert gates.season_progress("Premier League", 380, 20) == 1.0           # finished
    assert gates.season_progress("Premier League", 95, 20) == 0.25           # 9.5 games each of 38
    assert gates.season_progress("Premier League", 360, 20) == 1.0           # >= 90% counts as finished
    assert gates.season_progress("Champions League", 40, 36) == 1.0          # not a round-robin
    assert gates.season_progress("Premier League", 0, 20) == 1.0


def _aerial_totals(duels_op, won_op):
    return {1: {"aer_duels": duels_op, "aer_duels_op": duels_op, "aer_won_op": won_op, "aer_won_duels": won_op}}


def test_aerial_win_rate_appears_earlier_in_a_partial_season():
    totals = _aerial_totals(duels_op=4, won_op=3)
    assert finalize_aerial(totals)[1]["aer_win_rate_op_pct"] is None         # full-season gate: needs 10 duels
    gates.set_scale(0.25)
    assert finalize_aerial(totals)[1]["aer_win_rate_op_pct"] == 75.0         # quarter-season gate: 3 duels


def test_minutes_floor_shrinks_with_progress_but_not_below_three_matches():
    df = pd.DataFrame({"season_progress": [1.0, 0.5, 0.2, None]})
    assert list(config.minutes_floor(df)) == [450, 270, 270, 450]
    assert config.minutes_floor(pd.DataFrame({"x": [1]})) == config.ADV_MIN_MINUTES   # older data without the column


def test_every_category_module_that_gates_has_the_import():
    """A gate written as gates.gate(n) but with `gates` not imported only fails mid-rebuild."""
    import importlib, pathlib, re
    for f in pathlib.Path(config.__file__).parent.joinpath("categories").glob("*.py"):
        if "gates.gate(" in f.read_text(encoding="utf-8"):
            assert hasattr(importlib.import_module(f"core.advanced.categories.{f.stem}"), "gates"), f.name


def test_sample_info_flags_an_in_progress_season():
    from core.advanced.summary import sample_info
    done = sample_info(2000, 38)
    assert done["early_season"] is False and done["early_note"] == ""
    early = sample_info(771, 9, floor=config.minutes_floor_for(0.24), progress=0.24)
    assert early["early_season"] is True and "24%" in early["early_note"]
    assert early["limited"] is False                       # 771 min >= the 270 floor: the existing 'limited' chip stays off
    assert config.minutes_floor_for(None) == 450 and config.minutes_floor_for(0.24) == 270 and config.minutes_floor_for(0.8) == 360
