"""
Unattended weekly data refresh: scrapes the current season for every league,
rebuilds the parquet, runs the data health check, and (if anything actually
changed) commits and pushes so a Render auto-deploy picks up fresh data.

Runs as a single in-process script (imports scrape()/main()/check_league_seasons()
directly rather than shelling out to separate python.exe calls) specifically so
the Windows Scheduled Task that launches this via pythonw.exe never has a
console window to suppress in the first place -- there's nothing to open.

Everything is logged to auto_update.log since pythonw.exe has no console to
print to. Check that file, not stdout, if you want to see what happened.

    python scraping/auto_update.py            # normal run
    python scraping/auto_update.py --no-push   # scrape + rebuild only, skip git

See scraping/setup_scheduled_task.py for the Task Scheduler registration
(weekly, catch-up-if-missed, AC-power-only, hidden window).
"""
import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.advanced import config
from scraping.scrape_whoscored import scrape
from scraping.build_advanced_metrics import main as rebuild_parquet
from scraping.check_data_health import check_league_seasons

LOG_PATH = Path(__file__).parent / "auto_update.log"
CURRENT_SEASON = "2025-26"
WORKERS = 2  # matches the value already validated as safe in this session


def log(msg: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    try:
        print(line, flush=True)  # no-op under pythonw.exe, harmless
    except Exception:
        pass


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


def run(push: bool = True) -> None:
    log("=== auto_update starting ===")

    try:
        leagues = list(config.LEAGUE_DIR_MAP.keys())
        log(f"Scraping {len(leagues)} leagues, season {CURRENT_SEASON}, {WORKERS} workers")
        scrape(leagues, [CURRENT_SEASON], headless=False, workers=WORKERS)
        log("Scrape done")
    except Exception:
        log("!!! scrape failed, aborting this run (last week's data stays in place)")
        import traceback
        log(traceback.format_exc())
        return

    try:
        log("Rebuilding parquet...")
        t0 = time.time()
        rebuild_parquet()
        log(f"Rebuild done in {time.time()-t0:.1f}s")
    except Exception:
        log("!!! rebuild failed, aborting this run (last week's parquet stays in place)")
        import traceback
        log(traceback.format_exc())
        return

    # A flagged health check should never block this week's data from
    # shipping -- it's a signal to look into later, not a reason to hold
    # back real data (same principle Grid Sentinel's workflow uses: a
    # non-critical step's failure must never block the day's actual data).
    try:
        results = check_league_seasons(threshold=0.05)
        flagged = [r for r in results if r["flagged"]]
        if flagged:
            log(f"Health check: {len(flagged)} league-season(s) flagged above 5% unusable:")
            for r in flagged:
                log(f"  - {r['league']} {r['season']}: {r['bad']}/{r['total']} unusable ({r['rate']*100:.1f}%)")
        else:
            log("Health check: all league-seasons within acceptable range")
    except Exception:
        log("!!! health check itself failed (non-fatal, continuing)")
        import traceback
        log(traceback.format_exc())

    if not push:
        log("--no-push passed, skipping git commit/push")
        log("=== auto_update complete ===")
        return

    status = git("status", "--porcelain", "data/advanced/")
    if not status.stdout.strip():
        log("No data changes this run (no new matches since last week) — nothing to commit")
        log("=== auto_update complete ===")
        return

    log("Data changed, committing and pushing...")
    git("add", "data/advanced/")
    commit_msg = f"Weekly auto-update: refresh {CURRENT_SEASON} data ({datetime.now():%Y-%m-%d})"
    commit = git("commit", "-m", commit_msg)
    if commit.returncode != 0:
        log(f"!!! commit failed: {commit.stderr.strip()}")
        log("=== auto_update complete (commit failed) ===")
        return
    push_result = git("push", "origin", "main")
    if push_result.returncode != 0:
        log(f"!!! push failed: {push_result.stderr.strip()}")
    else:
        log("Pushed successfully")

    log("=== auto_update complete ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-push", action="store_true", help="Scrape + rebuild only, skip git commit/push")
    args = parser.parse_args()
    run(push=not args.no_push)
