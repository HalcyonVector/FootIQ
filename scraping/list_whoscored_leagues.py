"""
One-off discovery script: prints WhoScored's own current region/tournament
names, so new leagues get added to soccerdata's config with the EXACT string
WhoScored uses right now (sponsor names change — e.g. Eredivisie/Portugal's
top flight aren't always just the plain name), instead of guessed strings
that would silently 404 when scraping starts.

Usage:
    python scraping/list_whoscored_leagues.py                # print everything
    python scraping/list_whoscored_leagues.py championship eredivisie portugal liga champions europa
                                                               # filter by keyword (case-insensitive, matches region or league name)
"""

import sys
import re as _re
import json as _json
from pathlib import Path

import soccerdata.whoscored as ws_mod

LOG_PATH = Path(__file__).parent / "scrape_progress.log"


class PatchedJson:
    """Same fix as scrape_whoscored.py: soccerdata 1.9.0 wraps var=None
    responses in '<html><body>{json}</body></html>' but json.load()s them
    directly, which throws. Strip the wrapper before parsing."""

    @staticmethod
    def load(fp):
        raw = fp.read()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        m = _re.search(r"<body[^>]*>(.*)</body>", raw, _re.S)
        if m:
            raw = m.group(1)
        return _json.loads(raw)

    dumps = staticmethod(_json.dumps)
    JSONDecodeError = _json.JSONDecodeError


ws_mod.json = PatchedJson

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


def main() -> None:
    import soccerdata as sd

    keywords = [k.lower() for k in sys.argv[1:]]

    # Any already-known league works here - we only need a live Selenium
    # session, read_leagues() itself isn't used since it filters down to
    # already-configured leagues. We want the FULL universe WhoScored serves.
    ws = sd.WhoScored(leagues="ENG-Premier League", seasons="2024-25", headless=False)

    filepath = ws.data_dir / "tiers.json"
    reader = ws.get("https://www.whoscored.com", filepath, var="allRegions", no_cache=True)
    data = _json.load(reader)

    rows = []
    for region in data:
        for league in region["tournaments"]:
            rows.append(f"{region['name']} - {league['name']}")

    rows.sort()

    if keywords:
        rows = [r for r in rows if any(k in r.lower() for k in keywords)]

    print(f"\n{len(rows)} matching league(s):\n")
    for r in rows:
        print(f'  "{r}"')
    print()


if __name__ == "__main__":
    main()
