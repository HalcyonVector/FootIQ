"""
Ships data/advanced (the ~250 MB of parquet) OUTSIDE git, as a GitHub Release
asset, so neither repo history nor a quota ever grows with it.

Why: the parquet used to live in Git LFS. GitHub's free LFS is 1 GB storage
+ 1 GB/month bandwidth, and every Render deploy re-downloaded ~250 MB of it
(plus weekly auto-updates re-uploading changed partitions), which doesn't fit
a free tier. Release assets are not metered against LFS, and git itself now
holds only a tiny pointer file: data/DATA_VERSION.

    python scraping/data_release.py fetch      # download + verify + install (Render build, fresh clone)
    python scraping/data_release.py publish    # zip data/advanced, upload as a release asset, write DATA_VERSION
    python scraping/data_release.py pack       # zip only (no upload), prints the sha256

Flow for a data update (scraping/auto_update.py does all of this):
    build parquet -> publish -> git add data/DATA_VERSION -> commit -> push
The upload happens BEFORE the push, so a deploy never sees a DATA_VERSION that
points at an asset which doesn't exist yet. Assets are immutable and named by
content hash; the last KEEP_ASSETS are kept so a deploy of an older commit
(rollback) still finds its data.

Stdlib only on purpose: it runs in Render's build step before anything else is
guaranteed, and `publish` shells out to the GitHub CLI (`gh`) that is already
logged in on this machine.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "advanced"
VERSION_FILE = ROOT / "data" / "DATA_VERSION"
INSTALLED_MARK = DATA_DIR / ".data_version"

REPO = os.environ.get("FOOTIQ_DATA_REPO", "HalcyonVector/FootIQ")
TAG = "data"
KEEP_ASSETS = 2
CHUNK = 1 << 20
FIXED_TIME = (2020, 1, 1, 0, 0, 0)   # zip entries get a constant timestamp so identical data => identical zip


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _data_files(data_dir: Path):
    for p in sorted(data_dir.rglob("*")):
        if p.is_file() and p.name != INSTALLED_MARK.name:
            yield p


def pack(out_zip: Path, data_dir: Path = DATA_DIR) -> dict:
    """Deterministic, uncompressed zip (parquet is already compressed)."""
    if not data_dir.is_dir() or not any(data_dir.rglob("*.parquet")):
        raise SystemExit(f"nothing to pack: no parquet under {data_dir}")
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_STORED) as zf:
        for p in _data_files(data_dir):
            info = zipfile.ZipInfo(p.relative_to(data_dir).as_posix(), FIXED_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            with open(p, "rb") as src, zf.open(info, "w") as dst:
                shutil.copyfileobj(src, dst, CHUNK)
    digest = _sha256(out_zip)
    return {"asset": f"footiq-data-{digest[:12]}.zip", "sha256": digest, "bytes": out_zip.stat().st_size}


def _gh(*args: str, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args, "--repo", REPO], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=check)


def publish(data_dir: Path = DATA_DIR, version_file: Path = VERSION_FILE) -> bool:
    """Upload the current data. Returns True if DATA_VERSION changed."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_zip = Path(tmp) / "pack.zip"
        meta = pack(tmp_zip, data_dir)
        old = json.loads(version_file.read_text()) if version_file.exists() else {}
        if old.get("sha256") == meta["sha256"]:
            print(f"[data] unchanged ({meta['asset']}), nothing to upload")
            return False

        named = Path(tmp) / meta["asset"]
        tmp_zip.rename(named)
        if _gh("release", "view", TAG, check=False).returncode != 0:
            _gh("release", "create", TAG, "--title", "FootIQ data",
                "--notes", "Parquet datasets for the app. Managed by scraping/data_release.py; do not edit.")
        print(f"[data] uploading {meta['asset']} ({meta['bytes']/1e6:.0f} MB)...", flush=True)
        _gh("release", "upload", TAG, str(named), "--clobber")

    meta["built"] = date.today().isoformat()
    meta["url"] = f"https://github.com/{REPO}/releases/download/{TAG}/{meta['asset']}"
    version_file.write_text(json.dumps(meta, indent=2) + "\n")
    _prune_assets(keep=meta["asset"], previous=old.get("asset"))
    print(f"[data] published {meta['asset']}")
    return True


def _prune_assets(keep: str, previous: str | None) -> None:
    """Drop old assets beyond KEEP_ASSETS (newest + the one before it)."""
    out = _gh("release", "view", TAG, "--json", "assets", check=False)
    if out.returncode != 0:
        return
    assets = sorted(json.loads(out.stdout).get("assets", []), key=lambda a: a.get("createdAt", ""), reverse=True)
    keepers = {keep, previous} - {None}
    for a in assets[KEEP_ASSETS:]:
        if a["name"] not in keepers:
            _gh("release", "delete-asset", TAG, a["name"], "--yes", check=False)


def installed_sha(data_dir: Path = DATA_DIR) -> str | None:
    mark = data_dir / INSTALLED_MARK.name
    return mark.read_text().strip() if mark.exists() else None


def fetch(force: bool = False, version_file: Path = VERSION_FILE, data_dir: Path = DATA_DIR) -> bool:
    """Download + verify + install the data named by DATA_VERSION.
    Returns True if it installed something, False if already up to date.
    Exits non-zero on any failure so a Render build fails loudly and the
    previous (working) deploy keeps serving."""
    if not version_file.exists():
        raise SystemExit(f"{version_file} missing: nothing to fetch (run `publish` first)")
    meta = json.loads(version_file.read_text())
    if not force and installed_sha(data_dir) == meta["sha256"]:
        print(f"[data] already at {meta['asset']}")
        return False

    url = os.environ.get("FOOTIQ_DATA_URL") or meta["url"]
    print(f"[data] downloading {url} ({meta['bytes']/1e6:.0f} MB)...", flush=True)
    data_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=data_dir.parent) as tmp:
        zpath = Path(tmp) / "data.zip"
        req = urllib.request.Request(url, headers={"User-Agent": "footiq-data-fetch"})
        with urllib.request.urlopen(req, timeout=120) as resp, open(zpath, "wb") as out:
            shutil.copyfileobj(resp, out, CHUNK)
        got = _sha256(zpath)
        if got != meta["sha256"]:
            raise SystemExit(f"checksum mismatch: expected {meta['sha256'][:12]}, got {got[:12]}")

        staging = Path(tmp) / "advanced"
        with zipfile.ZipFile(zpath) as zf:
            for name in zf.namelist():                       # no path traversal out of staging
                if Path(name).is_absolute() or ".." in Path(name).parts:
                    raise SystemExit(f"unsafe path in archive: {name}")
            zf.extractall(staging)
        (staging / INSTALLED_MARK.name).write_text(meta["sha256"])

        old = Path(tmp) / "old"
        if data_dir.exists():
            data_dir.rename(old)
        staging.rename(data_dir)
    print(f"[data] installed {meta['asset']}")
    return True


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--force", action="store_true")
    sub.add_parser("publish")
    p = sub.add_parser("pack")
    p.add_argument("out", nargs="?", default="footiq-data.zip")
    args = ap.parse_args(argv)
    if args.cmd == "fetch":
        fetch(force=args.force)
    elif args.cmd == "publish":
        publish()
    else:
        meta = pack(Path(args.out))
        print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
