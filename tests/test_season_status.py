"""The season pickers open on the newest mostly-played season and mark newer ones in progress."""
import json

from core.advanced import extras


def _write(tmp_path, monkeypatch, rows):
    f = tmp_path / "extras.json"
    f.write_text(json.dumps({"coverage": rows}), encoding="utf-8")
    monkeypatch.setattr(extras, "EXTRAS_JSON", str(f))


def _rows(season, *progress):
    return [{"league": f"L{i}", "season": season, "progress": p} for i, p in enumerate(progress)]


def test_defaults_to_newest_season_that_is_mostly_played(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, _rows("2026-27", 0.3, 0.26, 0.35) + _rows("2025-26", 1.0, 1.0, 0.97))
    assert extras.season_status(["2026-27", "2025-26", "2024-25"]) == ("2025-26", ["2026-27"])


def test_a_finished_current_season_is_the_default(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, _rows("2026-27", 1.0, 0.98, 1.0) + _rows("2025-26", 1.0, 1.0))
    assert extras.season_status(["2026-27", "2025-26"]) == ("2026-27", [])


def test_one_slow_competition_does_not_hold_the_default_back(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, _rows("2026-27", 0.95, 0.97, 0.4))          # the median decides, not the slowest
    assert extras.season_status(["2026-27", "2025-26"])[0] == "2026-27"


def test_missing_file_falls_back_to_the_first_season(tmp_path, monkeypatch):
    monkeypatch.setattr(extras, "EXTRAS_JSON", str(tmp_path / "nope.json"))
    assert extras.season_status(["2026-27", "2025-26"]) == ("2026-27", [])
