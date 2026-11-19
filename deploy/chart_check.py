"""Draws every chart on the site in a headless browser and fails if any of them breaks.

    py -3 -X utf8 deploy/chart_check.py                     # starts its own copy of the app on port 5099
    py -3 -X utf8 deploy/chart_check.py http://localhost:5000
    py -3 -X utf8 deploy/chart_check.py https://footiq-app.vercel.app

The Python tests only cover the server. A chart is drawn by static/js/charts.js in the browser, and a
mistake there (one renderer referring to a variable that only exists in another) turned every pass map
into "This chart could not be drawn" while all the tests passed. This opens the pages people use,
clicks through every tab, every team plot and every player-type plot, and counts:

  - charts that show "This chart could not be drawn" (a renderer threw),
  - error cards ("Could not load this.") where a request failed,
  - uncaught JavaScript errors and console errors.

Any of those fails the run (exit 1). Charts that say "No data" are fine: some players have no events of
a kind. Uses the installed Google Chrome through Playwright, so no browser download is needed.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

try:
    from playwright.sync_api import Page, sync_playwright
except ImportError:                       # exit 2 = could not run (not the same as a chart failing)
    print("Playwright is not installed: py -3 -m pip install playwright")
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent
OWN_PORT = 5099

# A winger, a playmaker (on the default season) and a goalkeeper: their tabs draw different charts.
PLAYERS = [
    {"player_id": 472122, "league": "Premier League", "season": "2025-26"},     # Rayan, Bournemouth
    {"player_id": 123761},                                                      # Bruno Fernandes, default season
    {"player_id": 406564, "league": "Premier League", "season": "2025-26"},     # Djordje Petrovic, goalkeeper
]
COMPARE = {"p1_id": 472122, "p2_id": 123761, "p1_league": "Premier League", "p2_league": "Premier League",
           "p1_season": "2025-26", "p2_season": "2025-26"}
TEAM = {"league": "Premier League", "season": "2025-26", "team": "Arsenal"}

# What a page shows while it waits, and what a failure looks like.
BUSY = ".state-loading, .mini-spinner, .loading-spinner"
COUNT_JS = """(scope) => {
  const root = scope ? document.querySelector(scope) : document;
  if (!root) return null;
  const vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const empties = [...root.querySelectorAll('.fc-empty')].filter(vis).map(e => e.textContent.trim());
  return {
    drawn: [...root.querySelectorAll('.fc-host svg, .ov-svg, .lg-style-row, #lg-table-panel tbody tr')].filter(vis).length,
    broken: empties.filter(t => /could not be drawn/i.test(t)).length,
    nodata: empties.filter(t => !/could not be drawn/i.test(t)).length,
    errors: [...root.querySelectorAll('.state-error')].filter(vis).map(e => e.textContent.trim().slice(0, 80)),
  };
}"""

failures: list[str] = []


def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_warm(base: str, limit: float = 300) -> None:
    """Waits until /api/health says the data is loaded (a sleeping free-tier host takes about a minute)."""
    deadline = time.time() + limit
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base + "/api/health", timeout=20) as r:
                if b'"warm":true' in r.read().replace(b" ", b""):
                    return
        except Exception:
            pass
        time.sleep(2)
    raise SystemExit(f"{base} did not finish loading its data within {limit:.0f} s")


def start_own_server() -> subprocess.Popen:
    if port_open(OWN_PORT):
        raise SystemExit(f"port {OWN_PORT} is already in use; pass a URL to check a running server instead")
    env = {**os.environ, "PORT": str(OWN_PORT), "FLASK_DEBUG": "0", "PYTHONWARNINGS": "ignore"}
    log = open(ROOT / "dev" / "chart_check_server.log", "w", encoding="utf-8") if (ROOT / "dev").is_dir() else subprocess.DEVNULL
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    return subprocess.Popen([sys.executable, "-X", "utf8", "app.py"], cwd=ROOT, env=env, stdout=log,
                            stderr=subprocess.STDOUT, creationflags=flags)


def settle(page: Page, extra_ms: int = 400) -> None:
    """Waits for requests to finish and spinners to go away."""
    try:
        page.wait_for_load_state("networkidle", timeout=60_000)
    except Exception:
        pass
    try:
        page.wait_for_function(f"() => ![...document.querySelectorAll('{BUSY}')].some(e => e.offsetWidth || e.offsetHeight)",
                               timeout=45_000)
    except Exception:
        pass
    page.wait_for_timeout(extra_ms)


def record(name: str, page: Page, scope: str | None = None, need_drawn: int = 1) -> None:
    c = page.evaluate(COUNT_JS, scope)
    if c is None:
        failures.append(f"{name}: {scope} is missing from the page")
        print(f"  [FAIL] {name}: {scope} is missing")
        return
    problems = []
    if c["broken"]:
        problems.append(f"{c['broken']} chart(s) could not be drawn")
    if c["errors"]:
        problems.append("error card: " + "; ".join(c["errors"]))
    if c["drawn"] < need_drawn:
        problems.append(f"{c['drawn']} chart(s) drawn, expected at least {need_drawn}")
    status = "FAIL" if problems else "ok"
    detail = ", ".join(problems) if problems else f"{c['drawn']} drawn" + (f", {c['nodata']} with no data" if c["nodata"] else "")
    print(f"  [{status}] {name}: {detail}")
    if problems:
        failures.append(f"{name}: {', '.join(problems)}")


def open_page(page: Page, base: str, path: str, params: dict | None = None) -> None:
    page.goto(base + path + ("?" + urlencode(params) if params else ""), wait_until="domcontentloaded", timeout=90_000)
    settle(page, 800)


def set_select(page: Page, sel_id: str, value: str) -> None:
    """Sets a <select> (the site wraps them in its own dropdown) and fires its change handler."""
    page.evaluate("""([id, v]) => { const s = document.getElementById(id); s.value = v;
                     s.dispatchEvent(new Event('change', { bubbles: true })); }""", [sel_id, value])
    settle(page)


def options(page: Page, sel_id: str) -> list[str]:
    return page.evaluate("id => [...document.getElementById(id).options].map(o => o.value)", sel_id)


def check_players(page: Page, base: str) -> None:
    for p in PLAYERS:
        open_page(page, base, "/player", p)
        who = page.evaluate("() => (document.querySelector('.profile-name') || {}).textContent || ''").strip()
        label = f"player {who or p['player_id']}"
        record(f"{label} / season overview", page, "#overview-section")
        tabs = page.evaluate("() => [...document.querySelectorAll('.adv-tab-btn')].map(b => [b.dataset.cat, b.textContent.trim()])")
        if not tabs:
            failures.append(f"{label}: no metric tabs appeared")
            print(f"  [FAIL] {label}: no metric tabs appeared")
        for key, title in tabs:
            page.evaluate("k => document.querySelector(`.adv-tab-btn[data-cat='${k}']`).click()", key)
            settle(page)
            record(f"{label} / {title}", page, f"#adv-panel-{key}")


def check_compare(page: Page, base: str) -> None:
    open_page(page, base, "/compare", COMPARE)
    tabs = page.evaluate("() => [...document.querySelectorAll('.adv-tab-btn, .cmp-tab-btn, [data-cat]')]"
                         ".filter(b => b.tagName === 'BUTTON').map(b => b.dataset.cat)")
    record("compare / first view", page)
    for key in dict.fromkeys(k for k in tabs if k):
        page.evaluate("k => document.querySelector(`button[data-cat='${k}']`).click()", key)
        settle(page)
        record(f"compare / {key}", page)


def check_explore(page: Page, base: str) -> None:
    open_page(page, base, "/explore")
    set_select(page, "explore-view", "scatter")
    # the scatter waits for a metric on each axis: one from the first category, one from the second
    cats = [c for c in options(page, "explore-category") if c]
    for axis, cat in (("", cats[0]), ("-y", cats[min(1, len(cats) - 1)])):
        set_select(page, f"explore-category{axis}", cat)
        set_select(page, f"explore-metric{axis}", next(m for m in options(page, f"explore-metric{axis}") if m))
    record("explore / scatter", page)
    set_select(page, "explore-view", "quadrant")
    record("explore / quadrant", page)
    sel = "explore-quad"
    presets = options(page, sel)
    bad_before = len(failures)
    for v in presets:
        set_select(page, sel, v)
        c = page.evaluate(COUNT_JS, None)
        if c["broken"] or c["errors"] or c["drawn"] < 1:
            record(f"explore / quadrant {v}", page)
    print(f"  [{'ok' if len(failures) == bad_before else 'FAIL'}] explore / {len(presets)} quadrant plots")


def check_teams(page: Page, base: str) -> None:
    open_page(page, base, "/league", {"league": TEAM["league"], "season": TEAM["season"]})
    record("teams / how they play", page, "#lg-style-panel")
    for v in options(page, "lg-metric")[:3] + options(page, "lg-metric")[-2:]:
        set_select(page, "lg-metric", v)
    record("teams / how they play, other measures", page, "#lg-style-panel")
    page.click(".lg-tab[data-tab='map']")
    settle(page)
    plots = options(page, "lg-map")
    bad_before = len(failures)
    for v in plots:
        set_select(page, "lg-map", v)
        c = page.evaluate(COUNT_JS, "#lg-map-panel")
        if c["broken"] or c["errors"] or c["drawn"] < 1:
            record(f"teams / style map {v}", page, "#lg-map-panel")
    print(f"  [{'ok' if len(failures) == bad_before else 'FAIL'}] teams / {len(plots)} style map plots")
    page.click(".lg-tab[data-tab='table']")
    settle(page)
    record("teams / table", page, "#lg-table-panel")

    open_page(page, base, "/team", TEAM)
    record(f"team page {TEAM['team']}", page, None, need_drawn=3)


def main() -> int:
    base = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else None
    server = None
    if base is None:
        base = f"http://127.0.0.1:{OWN_PORT}"
        print(f"Starting the app on port {OWN_PORT}...")
        server = start_own_server()
    t0 = time.time()
    try:
        wait_warm(base)
        print(f"Checking charts on {base}")
        js_errors: list[str] = []
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(channel="chrome", headless=True)
            except Exception:
                try:
                    browser = pw.chromium.launch(headless=True)   # Playwright's own Chromium, if installed
                except Exception as e:
                    print(f"No browser to run the check in (install Google Chrome): {str(e).splitlines()[0]}")
                    return 2
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.on("pageerror", lambda e: js_errors.append(f"{page.url}: {e}"))
            page.on("console", lambda m: m.type == "error" and js_errors.append(f"{page.url}: {m.text[:300]}"))
            for name, step in [("players", check_players), ("compare", check_compare), ("explore", check_explore),
                               ("teams", check_teams)]:
                print(f"- {name}")
                try:
                    step(page, base)
                except Exception as e:                            # a missing element or a timeout is a failure too
                    failures.append(f"{name}: {type(e).__name__}: {str(e).splitlines()[0][:200]}")
                    print(f"  [FAIL] {name}: {type(e).__name__}: {str(e).splitlines()[0][:200]}")
            browser.close()
        for e in dict.fromkeys(js_errors):
            failures.append("JavaScript error: " + e)
    finally:
        if server:
            server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()
    print(f"\n{'FAILED' if failures else 'All charts drew'} in {time.time() - t0:.0f} s")
    for f in failures:
        print("  - " + f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
