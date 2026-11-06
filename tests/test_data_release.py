"""data_release: deterministic pack, verified fetch/install, and the failure modes
that must stop a Render build (bad checksum, missing version file)."""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scraping"))
import data_release as dr  # noqa: E402


def _make_data(root: Path, payload=b"abc"):
    (root / "league=A" / "season=1").mkdir(parents=True)
    (root / "league=A" / "season=1" / "x.parquet").write_bytes(payload)
    (root / "top.parquet").write_bytes(b"top")
    (root / "xg_model.json").write_text("{}")
    return root


def test_pack_is_deterministic_and_content_addressed(tmp_path):
    d = _make_data(tmp_path / "advanced")
    a = dr.pack(tmp_path / "a.zip", d)
    os.utime(d / "top.parquet", (1, 1))            # mtimes must not matter
    b = dr.pack(tmp_path / "b.zip", d)
    assert a["sha256"] == b["sha256"] and a["asset"] == f"footiq-data-{a['sha256'][:12]}.zip"
    (d / "top.parquet").write_bytes(b"changed")
    assert dr.pack(tmp_path / "c.zip", d)["sha256"] != a["sha256"]


def test_pack_refuses_empty_dir(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(SystemExit):
        dr.pack(tmp_path / "x.zip", tmp_path / "empty")


def _release(tmp_path, monkeypatch, tamper=False):
    src = _make_data(tmp_path / "src")
    meta = dr.pack(tmp_path / "asset.zip", src)
    if tamper:
        meta["sha256"] = "0" * 64
    meta["url"] = (tmp_path / "asset.zip").as_uri()
    vf = tmp_path / "DATA_VERSION"
    vf.write_text(json.dumps(meta))
    monkeypatch.delenv("FOOTIQ_DATA_URL", raising=False)
    return vf, meta


def test_fetch_installs_then_skips_when_current(tmp_path, monkeypatch):
    vf, meta = _release(tmp_path, monkeypatch)
    dest = tmp_path / "site" / "advanced"
    assert dr.fetch(version_file=vf, data_dir=dest) is True
    assert (dest / "top.parquet").read_bytes() == b"top"
    assert (dest / "league=A" / "season=1" / "x.parquet").exists()
    assert dr.installed_sha(dest) == meta["sha256"]
    assert dr.fetch(version_file=vf, data_dir=dest) is False       # already current
    assert dr.fetch(force=True, version_file=vf, data_dir=dest) is True


def test_fetch_replaces_older_install(tmp_path, monkeypatch):
    vf, _ = _release(tmp_path, monkeypatch)
    dest = tmp_path / "site" / "advanced"
    dest.mkdir(parents=True)
    (dest / "stale.parquet").write_bytes(b"old")
    dr.fetch(version_file=vf, data_dir=dest)
    assert not (dest / "stale.parquet").exists() and (dest / "top.parquet").exists()


def test_fetch_rejects_bad_checksum_and_keeps_existing_data(tmp_path, monkeypatch):
    vf, _ = _release(tmp_path, monkeypatch, tamper=True)
    dest = tmp_path / "site" / "advanced"
    dest.mkdir(parents=True)
    (dest / "keep.parquet").write_bytes(b"keep")
    with pytest.raises(SystemExit, match="checksum"):
        dr.fetch(version_file=vf, data_dir=dest)
    assert (dest / "keep.parquet").read_bytes() == b"keep"


def test_fetch_without_version_file_fails(tmp_path):
    with pytest.raises(SystemExit):
        dr.fetch(version_file=tmp_path / "nope", data_dir=tmp_path / "d")
