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
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import soccerdata.whoscored as ws_mod

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.advanced.config import all_domestic_seasons

LOG_PATH = Path(__file__).parent / "scrape_progress.log"

TOP5_LEAGUES = [
    "ENG-Premier League",
    "ESP-La Liga",
    "ITA-Serie A",
    "GER-Bundesliga",
    "FRA-Ligue 1",
]
# Computed from today's date (all_domestic_seasons()) rather than hardcoded —
# only matters for a manual `python scrape_whoscored.py` with no --seasons
# flag (auto_update.py always passes an explicit [CURRENT_SEASON]), but a
# stale hardcoded list here would be the same silent-staleness bug that hit
# CURRENT_SEASON, just for anyone running this by hand instead.
DEFAULT_SEASONS = all_domestic_seasons()

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
    """Same driver soccerdata builds, but the window is CREATED off-screen
    (window_position at launch) instead of being moved there after it already
    flashed onto the desktop and grabbed focus for a moment. Falls back to the
    stock init if this SeleniumBase version rejects the arguments."""
    import seleniumbase as sb
    try:
        if hasattr(self, "_driver"):
            self._driver.quit()
        proxy_str = self.proxy()
        driver = sb.Driver(
            uc=True,
            headless=self.headless,
            binary_location=self.path_to_browser,
            host_resolver_rules="MAP * ~NOTFOUND , EXCLUDE 127.0.0.1" if proxy_str is not None else None,
            proxy=proxy_str,
            window_position="-32000,-32000",
            window_size="1280,900",
        )
    except TypeError:
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


SCHEDULE_BACKOFF_S = (20, 60, 120, 180)   # waits between the 5 schedule attempts


def schedule_error_kind(exc: BaseException) -> str:
    """'not_published': WhoScored has no such season for this competition (the next
    Champions League / Euros season before it is listed) -- retrying can never help.
    'transient': anything else (bot-check page instead of JSON, missing Fixtures link...)."""
    if isinstance(exc, KeyError) and "are in the [index]" in str(exc):
        return "not_published"
    return "transient"


def _fetch_schedule(league: str, season: str, headless: bool):
    """(schedule | None, status) with status 'ok' | 'not_published' | 'schedule_failed'.
    Up to 5 attempts with growing waits and a brand-new Chrome from the 3rd on: the
    failures seen in practice (a block page instead of JSON, no 'Fixtures' link) clear
    up after a pause or a fresh browser session."""
    import soccerdata as sd

    def new_reader():
        return sd.WhoScored(leagues=league, seasons=season, headless=headless, path_to_browser=STABLE_CHROME)

    ws = new_reader()
    attempts = len(SCHEDULE_BACKOFF_S) + 1
    for attempt in range(attempts):
        try:
            return ws.read_schedule(), "ok"
        except Exception as exc:
            if schedule_error_kind(exc) == "not_published":
                log(f"{league} {season}: WhoScored has no such season yet -- skipping (not an error)")
                return None, "not_published"
            log(f"{league} {season}: schedule fetch failed (attempt {attempt + 1}/{attempts}):\n{traceback.format_exc()}")
            if attempt == attempts - 1:
                break
            time.sleep(SCHEDULE_BACKOFF_S[attempt])
            if attempt >= 1:
                try:
                    ws._driver.quit()
                except Exception:
                    pass
                ws = new_reader()
    log(f"!!! giving up on {league} {season} schedule after {attempts} attempts")
    return None, "schedule_failed"


def _scrape_one(league: str, season: str, headless: bool) -> tuple[str, str, list[int], str]:
    """Scrapes one (league, season) fully — schedule fetch (with retries) then
    every match's events, sequentially. Split out from scrape() so each can
    also be handed to its own worker process (own Selenium/Chrome instance)
    when running with workers > 1. Returns the match ids that failed plus the
    schedule status ('ok' | 'not_published' | 'schedule_failed')."""
    import soccerdata as sd

    log(f"=== {league} {season}: starting ===")
    schedule, status = _fetch_schedule(league, season, headless)
    if schedule is None:
        return league, season, [], status
    ws = sd.WhoScored(leagues=league, seasons=season, headless=headless, path_to_browser=STABLE_CHROME)

    sched_reset = schedule.reset_index()
    sched_reset["game_id"] = sched_reset["game_id"].astype(int)
    season_key = sched_reset["season"].iloc[0]  # soccerdata's normalized key, e.g. "2526"

    # Skip fixtures that haven't been played yet WITHOUT costing a single
    # request for them -- WhoScored's own schedule payload already carries
    # home_score/away_score per fixture (populated only once a match has
    # a final score), so "has this been played" is a column check against
    # data already in hand from the ONE schedule fetch above, not something
    # that needs guessing from today's date or a kickoff-time buffer.
    # Checked directly against the cached schedule for an in-progress season
    # (Eredivisie 2026-27): of 306 scheduled fixtures, exactly the 54 with a
    # recorded score matched the 54 that genuinely had event data, and all
    # 252 without one were exactly the ones WhoScored has nothing for yet --
    # a fully reliable split, not a heuristic. This is what actually fixes
    # the "recheck the whole season every run" cost for the WEEKLY job: a
    # future fixture now costs nothing at all, rather than the same one
    # real request a played match needs, just to learn it's empty.
    if "home_score" in sched_reset.columns and "away_score" in sched_reset.columns:
        played = sched_reset["home_score"].notna() & sched_reset["away_score"].notna()
        n_unplayed = int((~played).sum())
        if n_unplayed:
            log(f"{league} {season}: skipping {n_unplayed} fixture(s) with no final score yet (not requested at all)")
        sched_reset = sched_reset[played]

    match_ids = sched_reset["game_id"].tolist()
    log(f"{league} {season}: {len(match_ids)} matches in schedule")

    done = 0
    failed: list[int] = []
    for match_id in match_ids:
        cache_file = ws.data_dir / "events" / f"{league}_{season_key}" / f"{match_id}.json"
        already_cached = cache_file.exists()
        try:
            # force_cache=True: soccerdata's read_events() re-fetches the
            # LIVE season schedule from WhoScored on every single call by
            # default for an in-progress season (read_schedule()'s own
            # force_cache defaults to False specifically because an ongoing
            # season's fixture list can shift — postponements, rescheduled
            # dates). That's the right default for calling read_events() in
            # isolation, but here it means re-fetching the full paginated
            # schedule (10+ requests) before EVERY match in a loop that's
            # already fetched it fresh once, seconds ago, at line ~118 —
            # measured live as the majority of a ~4 min per-match cost across
            # a 380-fixture season. force_cache=True reuses that same-run
            # fetch for the rest of this run's matches instead of redoing it
            # every time; the schedule itself is still fetched live exactly
            # once per run (schedule = ws.read_schedule() above), so this
            # doesn't trade away the freshness read_schedule()'s default is
            # protecting -- it only removes 379 redundant re-fetches of data
            # this same run already has.
            ws.read_events(match_id=match_id, output_fmt=None, on_error="raise", force_cache=True)
            done += 1
            if not already_cached:
                log(f"{league} {season}: [{done}/{len(match_ids)}] scraped match {match_id}")
        except Exception:
            log(f"{league} {season}: match {match_id} FAILED:\n{traceback.format_exc()}")
            failed.append(match_id)

    log(f"=== {league} {season}: done ({done}/{len(match_ids)}) ===")
    return league, season, failed, "ok"


def scrape(leagues: list[str], seasons: list[str], headless: bool, workers: int = 1) -> dict:
    """Returns {"schedule_failed": [(league, season)], "not_published": [...], "matches_failed": n}
    so the caller can tell a quiet run from one that silently skipped a league."""
    tasks = [(league, season) for league in leagues for season in seasons]
    failed: list[tuple[str, str, int]] = []
    summary = {"schedule_failed": [], "not_published": [], "matches_failed": 0}

    def note(league, season, match_fails, status):
        failed.extend((league, season, mid) for mid in match_fails)
        if status in ("schedule_failed", "not_published"):
            summary[status].append((league, season))

    if workers <= 1:
        for league, season in tasks:
            _, _, match_fails, status = _scrape_one(league, season, headless)
            note(league, season, match_fails, status)
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
                    _, _, match_fails, status = fut.result()
                    note(league, season, match_fails, status)
                except Exception:
                    log(f"!!! worker for {league} {season} crashed:\n{traceback.format_exc()}")
                    summary["schedule_failed"].append((league, season))

    summary["matches_failed"] = len(failed)
    if failed:
        log(f"Finished with {len(failed)} failed matches: {failed}")
    if summary["schedule_failed"]:
        log(f"!!! SCHEDULE UNAVAILABLE (these competitions were NOT updated): {summary['schedule_failed']}")
    if summary["not_published"]:
        log(f"Not on WhoScored yet (skipped): {summary['not_published']}")
    if not failed and not summary["schedule_failed"]:
        log("Finished. No failures.")
    return summary


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
