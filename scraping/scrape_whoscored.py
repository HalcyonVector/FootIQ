"""
Overnight WhoScored event-data scraper (prototype).

Resumable by design: soccerdata caches each match's event JSON to disk
(no expiry) as soon as it's fetched, so if this gets killed — laptop
sleeps, Chrome crashes, whatever — just rerun it. Already-scraped
matches are skipped (read straight from the local cache), only the
remaining ones hit the network.

Usage:
    python scrape_whoscored.py
    python scrape_whoscored.py --leagues "ENG-Premier League" "ESP-La Liga" --seasons 2023-24 2024-25 2025-26

Progress is appended to scrape_progress.log in this folder so you can
check how far along it is without wading through Selenium/Chrome noise.
"""

import argparse
import json as _json
import re
import time
import traceback
from datetime import datetime
from pathlib import Path

import soccerdata.whoscored as ws_mod

LOG_PATH = Path(__file__).parent / "scrape_progress.log"

TOP5_LEAGUES = [
    "ENG-Premier League",
    "ESP-La Liga",
    "ITA-Serie A",
    "GER-Bundesliga",
    "FRA-Ligue 1",
]
DEFAULT_SEASONS = ["2023-24", "2024-25", "2025-26"]

# Pinned to stable Chrome explicitly: this machine's Chrome Dev channel runs
# ahead of seleniumbase's bundled driver (which matches stable Chrome), and
# undetected-chromedriver's auto-detection picks Chrome Dev if not told
# otherwise, causing a silent version-mismatch handshake failure ("cannot
# connect to chrome at 127.0.0.1:9222").
STABLE_CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


class PatchedJson:
    """soccerdata 1.9.0 saves var=None responses as
    '<html><body>{json}</body></html>' but then json.load()s them
    directly, which throws. Strip the wrapper before parsing.
    Only affects schedule/calendar reads, not the event JSON itself."""

    @staticmethod
    def load(fp):
        raw = fp.read()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        m = re.search(r"<body[^>]*>(.*)</body>", raw, re.S)
        if m:
            raw = m.group(1)
        return _json.loads(raw)

    dumps = staticmethod(_json.dumps)
    JSONDecodeError = _json.JSONDecodeError


ws_mod.json = PatchedJson

# Keep Chrome non-headless (lower bot-detection risk) but park the window
# off the visible desktop so it doesn't steal focus / pop up on screen.
# Off-screen (not minimized) avoids Chrome's background-tab JS throttling,
# which a minimized window would trigger.
import soccerdata._common as common_mod

_orig_init_webdriver = common_mod.BaseSeleniumReader._init_webdriver


def _init_webdriver_offscreen(self):
    driver = _orig_init_webdriver(self)
    try:
        driver.set_window_position(-32000, -32000)
    except Exception:
        pass
    return driver


common_mod.BaseSeleniumReader._init_webdriver = _init_webdriver_offscreen


def log(msg: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _scrape_one(league: str, season: str, headless: bool) -> tuple[str, str, list[int]]:
    """Scrapes one (league, season) fully — schedule fetch (with retries) then
    every match's events, sequentially. Split out from scrape() so each can
    also be handed to its own worker process (own Selenium/Chrome instance)
    when running with workers > 1. Returns the list of match ids that failed."""
    import soccerdata as sd

    log(f"=== {league} {season}: starting ===")
    ws = sd.WhoScored(leagues=league, seasons=season, headless=headless, path_to_browser=STABLE_CHROME)

    for attempt in range(3):
        try:
            schedule = ws.read_schedule()
            break
        except Exception:
            log(f"{league} {season}: schedule fetch failed (attempt {attempt + 1}/3):\n{traceback.format_exc()}")
            time.sleep(15)
    else:
        log(f"!!! giving up on {league} {season} schedule after 3 attempts")
        return league, season, []

    sched_reset = schedule.reset_index()
    sched_reset["game_id"] = sched_reset["game_id"].astype(int)
    match_ids = sched_reset["game_id"].tolist()
    season_key = sched_reset["season"].iloc[0]  # soccerdata's normalized key, e.g. "2526"
    log(f"{league} {season}: {len(match_ids)} matches in schedule")

    done = 0
    failed: list[int] = []
    for match_id in match_ids:
        cache_file = ws.data_dir / "events" / f"{league}_{season_key}" / f"{match_id}.json"
        already_cached = cache_file.exists()
        try:
            ws.read_events(match_id=match_id, output_fmt=None, on_error="raise")
            done += 1
            if not already_cached:
                log(f"{league} {season}: [{done}/{len(match_ids)}] scraped match {match_id}")
        except Exception:
            log(f"{league} {season}: match {match_id} FAILED:\n{traceback.format_exc()}")
            failed.append(match_id)

    log(f"=== {league} {season}: done ({done}/{len(match_ids)}) ===")
    return league, season, failed


def scrape(leagues: list[str], seasons: list[str], headless: bool, workers: int = 1) -> None:
    tasks = [(league, season) for league in leagues for season in seasons]
    failed: list[tuple[str, str, int]] = []

    if workers <= 1:
        for league, season in tasks:
            _, _, match_fails = _scrape_one(league, season, headless)
            failed.extend((league, season, mid) for mid in match_fails)
    else:
        import concurrent.futures

        log(f"Running {len(tasks)} (league, season) task(s) with {workers} parallel worker(s) — "
            f"each gets its own Chrome instance. If this gets blocked/flagged, rerun with "
            f"--workers 1 to fall back to sequential (already-cached matches are skipped either way).")
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_scrape_one, league, season, headless): (league, season) for league, season in tasks}
            for fut in concurrent.futures.as_completed(futures):
                league, season = futures[fut]
                try:
                    _, _, match_fails = fut.result()
                    failed.extend((league, season, mid) for mid in match_fails)
                except Exception:
                    log(f"!!! worker for {league} {season} crashed:\n{traceback.format_exc()}")

    if failed:
        log(f"Finished with {len(failed)} failed matches: {failed}")
    else:
        log("Finished. No failures.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--leagues", nargs="+", default=TOP5_LEAGUES)
    parser.add_argument("--seasons", nargs="+", default=DEFAULT_SEASONS)
    parser.add_argument("--headless", action="store_true", default=False,
                         help="Run Chrome headless. Off by default — a visible "
                              "browser is less likely to get flagged as a bot.")
    parser.add_argument("--workers", type=int, default=1,
                         help="Scrape this many (league, season) tasks concurrently, each "
                              "in its own Chrome instance. Default 1 (sequential, original "
                              "behavior). Higher values are faster but more likely to trip "
                              "WhoScored's bot detection since requests fan out from one IP.")
    args = parser.parse_args()

    log(f"Starting scrape: leagues={args.leagues} seasons={args.seasons} headless={args.headless} workers={args.workers}")
    scrape(args.leagues, args.seasons, args.headless, args.workers)
