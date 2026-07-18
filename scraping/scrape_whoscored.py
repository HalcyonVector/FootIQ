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


def scrape(leagues: list[str], seasons: list[str], headless: bool) -> None:
    import soccerdata as sd

    failed: list[tuple[str, str, int]] = []

    for league in leagues:
        for season in seasons:
            log(f"=== {league} {season}: starting ===")
            ws = sd.WhoScored(leagues=league, seasons=season, headless=headless)

            for attempt in range(3):
                try:
                    schedule = ws.read_schedule()
                    break
                except Exception:
                    log(f"schedule fetch failed (attempt {attempt + 1}/3):\n{traceback.format_exc()}")
                    time.sleep(15)
            else:
                log(f"!!! giving up on {league} {season} schedule after 3 attempts")
                continue

            sched_reset = schedule.reset_index()
            sched_reset["game_id"] = sched_reset["game_id"].astype(int)
            match_ids = sched_reset["game_id"].tolist()
            season_key = sched_reset["season"].iloc[0]  # soccerdata's normalized key, e.g. "2526"
            log(f"{league} {season}: {len(match_ids)} matches in schedule")

            done = 0
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
                    failed.append((league, season, match_id))

            log(f"=== {league} {season}: done ({done}/{len(match_ids)}) ===")

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
    args = parser.parse_args()

    log(f"Starting scrape: leagues={args.leagues} seasons={args.seasons} headless={args.headless}")
    scrape(args.leagues, args.seasons, args.headless)
