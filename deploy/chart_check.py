"""Draws every chart on the site in a headless browser and fails if any of them breaks.

    py -3 -X utf8 deploy/chart_check.py                     # starts its own copy of the app on port 5099
    py -3 -X utf8 deploy/chart_check.py http://localhost:5000
    py -3 -X utf8 deploy/chart_check.py https://footiq-app.vercel.app
    py -3 -X utf8 deploy/chart_check.py --phone-only           # or --desktop-only

The Python tests only cover the server. A chart is drawn by static/js/charts.js in the browser, and a
mistake there (one renderer referring to a variable that only exists in another) turned every pass map
into "This chart could not be drawn" while all the tests passed. This opens the pages people use,
clicks through every tab, every team plot and every player-type plot, and counts:

  - charts that show "This chart could not be drawn" (a renderer threw),
  - error cards ("Could not load this.") where a request failed,
  - uncaught JavaScript errors and console errors.

It then does the same at phone size (390px wide, touch, tabs through the phone's dropdown) for a
winger and a goalkeeper and a sample of the plots, and also fails if a page scrolls sideways or a
chart's text renders smaller than 8px (a desktop-sized canvas squeezed into a phone-sized box).
In both passes it scrolls the long pages (player, compare, team, coverage) half a screen at a time and
fails if a card stays invisible on screen (the fade-in once never fired for a card ~10 screens tall).

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
# Phone pass only: the page must not scroll sideways, and chart text must stay readable. A chart drawn on
# a desktop-sized canvas and squeezed into a ~270px box shrinks its 10px labels to 4px.
MIN_TEXT_PX = 8
LAYOUT_JS = """([scope, minPx]) => {
  const root = scope ? document.querySelector(scope) : document;
  const W = window.innerWidth, vis = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const name = el => el.id ? '#' + el.id : el.tagName.toLowerCase() + (el.classList.length ? '.' + [...el.classList].join('.') : '');
  const wide = [];
  if (document.documentElement.scrollWidth > W + 1) {
    document.querySelectorAll('body *').forEach(el => {
      if (!vis(el) || el.getBoundingClientRect().right <= W + 1) return;
      for (let p = el.parentElement; p; p = p.parentElement)
        if (/(auto|scroll|hidden)/.test(getComputedStyle(p).overflowX)) return;     // inside its own scroller
      if (el.parentElement && el.parentElement.getBoundingClientRect().right > W + 1) return;  // report the outermost
      wide.push(name(el));
    });
  }
  const tiny = [];
  (root ? root.querySelectorAll('svg') : []).forEach(svg => {
    if (!vis(svg)) return;
    const h = [...svg.querySelectorAll('text')].filter(t => t.textContent.trim())
      .map(t => t.getBoundingClientRect().height).filter(x => x > 0).sort((a, b) => a - b);
    if (h.length && h[Math.floor(h.length / 2)] < minPx)
      tiny.push(`${svg.getAttribute('aria-label') || name(svg.closest('[id]') || svg)} (${h[Math.floor(h.length / 2)].toFixed(1)}px)`);
  });
  return { scrollW: document.documentElement.scrollWidth, W, wide: [...new Set(wide)].slice(0, 5), tiny };
}"""

# Cards fade in (base.html) when they scroll into view. Anything still hidden while it sits well inside
# the screen (above the bottom 10%, which is where the fade starts) after the fade had time to run is a
# blank patch the visitor sees. A card taller than ~10 screens once stayed hidden like that for good.
HIDDEN_JS = """() => { const H = innerHeight; return [...document.querySelectorAll('.reveal:not(.in-view)')].filter(e => {
  const r = e.getBoundingClientRect(); return r.height > 0 && r.bottom > 0 && r.top < H * 0.9; })
  .map(e => (e.id ? '#' + e.id : '.' + [...e.classList].join('.')) + ' (' + Math.round(e.getBoundingClientRect().height) + 'px tall)'); }"""

failures: list[str] = []
PHONE = {"on": False}            # set during the phone pass; adds the layout checks to every record()


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
    if PHONE["on"]:
        name = "phone / " + name
    # Some tabs load in two steps (Link-Up fetches the teammates, then the detail), and a slow host
    # leaves a quiet gap between them: give the charts up to 25 s to appear before judging.
    try:
        page.wait_for_function(f"""(scope) => {{ const c = ({COUNT_JS})(scope);
            return !c || c.broken || c.errors.length || c.drawn >= {need_drawn}; }}""", arg=scope, timeout=25_000)
    except Exception:
        pass
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
    if PHONE["on"]:
        lay = page.evaluate(LAYOUT_JS, [scope, MIN_TEXT_PX])
        if lay["scrollW"] > lay["W"] + 1:
            problems.append(f"page scrolls sideways ({lay['scrollW']}px wide on a {lay['W']}px screen): " + ", ".join(lay["wide"]))
        if lay["tiny"]:
            problems.append(f"chart text under {MIN_TEXT_PX}px: " + "; ".join(lay["tiny"]))
    status = "FAIL" if problems else "ok"
    detail = ", ".join(problems) if problems else f"{c['drawn']} drawn" + (f", {c['nodata']} with no data" if c["nodata"] else "")
    print(f"  [{status}] {name}: {detail}")
    if problems:
        failures.append(f"{name}: {', '.join(problems)}")


def scroll_through(name: str, page: Page) -> None:
    """Scrolls the whole page half a screen at a time and fails if a card stays invisible on screen."""
    if PHONE["on"]:
        name = "phone / " + name
    page.evaluate("document.documentElement.style.scrollBehavior = 'auto'")
    step, y, stuck, stops = page.viewport_size["height"] // 2, 0, {}, 0
    while y < page.evaluate("document.documentElement.scrollHeight"):
        page.evaluate(f"window.scrollTo(0, {y})")
        page.wait_for_timeout(450)                  # the fade starts at once; give the observer a frame or two
        hidden = page.evaluate(HIDDEN_JS)
        if hidden:                                  # look again before blaming it: a slow frame is not a blank card
            page.wait_for_timeout(900)
            hidden = page.evaluate(HIDDEN_JS)
        for el in hidden:
            stuck[el] = stuck.get(el, 0) + 1
        y += step
        stops += 1
    page.evaluate("window.scrollTo(0, 0)")
    if stuck:
        detail = "; ".join(f"{el} hidden at {n} of {stops} scroll positions" for el, n in stuck.items())
        failures.append(f"{name}: blank while scrolling: {detail}")
        print(f"  [FAIL] {name}: blank while scrolling: {detail}")
    else:
        print(f"  [ok] {name}: nothing stays hidden while scrolling ({stops} positions)")


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
    for p in ([PLAYERS[0], PLAYERS[2]] if PHONE["on"] else PLAYERS):
        open_page(page, base, "/player", p)
        who = page.evaluate("() => (document.querySelector('.profile-name') || {}).textContent || ''").strip()
        label = f"player {who or p['player_id']}"
        record(f"{label} / season overview", page, "#overview-section")
        if p is PLAYERS[0]:
            scroll_through(f"{label} / scroll", page)
        tabs = page.evaluate("() => [...document.querySelectorAll('.adv-tab-btn')].map(b => [b.dataset.cat, b.textContent.trim()])")
        if not tabs:
            failures.append(f"{label}: no metric tabs appeared")
            print(f"  [FAIL] {label}: no metric tabs appeared")
        for key, title in tabs:
            if PHONE["on"]:                   # phones get a dropdown instead of the tab row
                set_select(page, "adv-tab-select", key)
            else:
                page.evaluate("k => document.querySelector(`.adv-tab-btn[data-cat='${k}']`).click()", key)
                settle(page)
            record(f"{label} / {title}", page, f"#adv-panel-{key}")


PASSES_SHOWN_JS = r"""() => { const st = document.querySelector('#adv-panel-passing .fc-stats');
  const m = st && st.innerText.match(/([\d,]+)\s*Passes/); return m ? +m[1].replace(/,/g, '') : null; }"""


def check_season_switch(page: Page, base: str) -> None:
    """Switching season in place must redraw the charts for the new season. The browser's chart
    cache was keyed by tab and filter only, so the Passing tab kept the previous season's (or the
    previous player's) pass map: a 4-pass map on a player with 1,037 passes."""
    p = PLAYERS[0]
    open_page(page, base, "/player", p)
    record("season switch / before", page, "#adv-panel-passing")
    choices = page.evaluate("() => [...document.querySelectorAll('#season-switch-slot select option')].map(o => o.value)")
    target = next((v for v in choices if v != f"{p['league']}|{p['season']}"), None)
    if not target:
        print("  [skip] season switch: this player has one season")
        return
    league, season = target.split("|")
    expected = page.evaluate("""async ([pid, league, season]) => {
        const r = await fetch('/api/category-chart', {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({player_id: pid, league, season, category: 'passing', filter: 'progressive', scope: 'all'})});
        const d = await r.json(); const m = (d.charts || []).find(c => c.key === 'map');
        const st = m && (m.spec.stats || []).find(x => x[0] === 'Passes'); return st ? st[1] : null; }""",
        [p["player_id"], league, season])
    page.evaluate("v => { const s = document.querySelector('#season-switch-slot select'); s.value = v;"
                  " s.dispatchEvent(new Event('change', { bubbles: true })); }", target)
    shown = None
    for _ in range(50):                       # up to ~25 s for the new season's charts
        page.wait_for_timeout(500)
        shown = page.evaluate(PASSES_SHOWN_JS)
        if shown == expected:
            break
    name = f"season switch to {league} {season}"
    if expected is None:
        print(f"  [skip] {name}: the server has no pass map to compare against")
    elif shown == expected:
        print(f"  [ok] {name}: pass map shows {shown} passes, as the server does")
    else:
        failures.append(f"{name}: pass map shows {shown} passes, the server has {expected}")
        print(f"  [FAIL] {name}: pass map shows {shown} passes, the server has {expected}")


SLOW_FETCH_JS = """(() => { const real = window.fetch.bind(window);
  window.fetch = async (url, opts) => {
    const key = String(url) + ' ' + ((opts && opts.body) || '');
    const res = await real(url, opts);
    if ((window.__slow || []).some(s => key.includes(s))) await new Promise(r => setTimeout(r, 6000));
    return res;
  }; })();"""


def check_slow_answers(page: Page, base: str) -> None:
    """A slow answer for the previous choice must not draw over the newer one. The first season's
    advanced stats (or the first competition's table) are held back 6 s inside the page while the
    choice changes; the page must end on the newer choice. Desktop only: the logic is the same."""
    if PHONE["on"]:
        return
    p = page.context.new_page()
    try:
        pl = PLAYERS[0]
        p.add_init_script(SLOW_FETCH_JS + f"window.__slow = ['\"season\":\"{pl['season']}\"'];")
        p.goto(base + "/player?" + urlencode(pl), wait_until="domcontentloaded", timeout=90_000)
        p.wait_for_selector("#season-switch-slot select", timeout=90_000)
        target = p.evaluate("s => [...document.querySelectorAll('#season-switch-slot select option')].map(o => o.value)"
                            ".find(v => !v.endsWith('|' + s))", pl["season"])
        if target:
            p.evaluate("v => { const s = document.querySelector('#season-switch-slot select'); s.value = v;"
                       " s.dispatchEvent(new Event('change', { bubbles: true })); }", target)
            p.wait_for_timeout(18_000)
            league, season = target.split("|")
            want = p.evaluate("""async ([pid, league, season]) => { const r = await fetch('/api/advanced-stats', {method: 'POST',
                headers: {'Content-Type': 'application/json'}, body: JSON.stringify({player_id: pid, league, season, scope: 'all'})});
                const d = await r.json(); return d.composite ? String(d.composite.score) : ''; }""", [pl["player_id"], league, season])
            shown = p.evaluate("() => (document.querySelector('#profile-score-slot .score-num') || {}).textContent || ''")
            verdict(f"slow answer / player rating after switching to {league} {season}", shown == want,
                    f"shows {shown}, the new season's rating is {want}")
        p.add_init_script("window.__slow = ['league-table?league=Premier'];")
        p.goto(base + "/league?" + urlencode({"league": "Premier League", "season": TEAM["season"]}),
               wait_until="domcontentloaded", timeout=90_000)
        p.wait_for_timeout(1500)
        p.evaluate("() => { const s = document.getElementById('lg-league'); s.value = 'La Liga';"
                   " s.dispatchEvent(new Event('change', { bubbles: true })); }")
        p.wait_for_timeout(10_000)
        title = p.evaluate("() => document.getElementById('lg-title').textContent")
        verdict("slow answer / Teams table after switching to La Liga", title.startswith("La Liga"), f"title is '{title}'")
    finally:
        p.close()


def verdict(name: str, ok: bool, detail: str) -> None:
    if ok:
        print(f"  [ok] {name}: {detail}")
    else:
        failures.append(f"{name}: {detail}")
        print(f"  [FAIL] {name}: {detail}")


def check_compare(page: Page, base: str) -> None:
    open_page(page, base, "/compare", COMPARE)
    tabs = page.evaluate("() => [...document.querySelectorAll('.adv-tab-btn, .cmp-tab-btn, [data-cat]')]"
                         ".filter(b => b.tagName === 'BUTTON').map(b => b.dataset.cat)")
    record("compare / first view", page)
    scroll_through("compare / scroll", page)
    for key in list(dict.fromkeys(k for k in tabs if k))[:3 if PHONE["on"] else None]:
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
    presets = options(page, sel)[:8 if PHONE["on"] else None]      # the phone pass samples the shared renderer
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
    plots = options(page, "lg-map")[:4 if PHONE["on"] else None]
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
    scroll_through(f"team page {TEAM['team']} / scroll", page)


def check_other_pages(page: Page, base: str) -> None:
    """Pages without charts: they still must load without errors (and, on a phone, fit the screen)."""
    for path in ("/", "/scout", "/coverage"):
        open_page(page, base, path)
        record(f"page {path}", page, None, need_drawn=0)
        if path == "/coverage":
            scroll_through("page /coverage / scroll", page)


PASSES = {
    "desktop": {"viewport": {"width": 1440, "height": 900}},
    "phone": {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True, "device_scale_factor": 2},
}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    base = args[0].rstrip("/") if args else None
    passes = [p for p in PASSES if f"--{p}-only" in sys.argv] or list(PASSES)
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
            for pass_name in passes:
                PHONE["on"] = pass_name == "phone"
                ctx = browser.new_context(**PASSES[pass_name])
                page = ctx.new_page()
                page.on("pageerror", lambda e, pg=page: js_errors.append(f"{pg.url}: {e}"))
                page.on("console", lambda m, pg=page: m.type == "error" and js_errors.append(f"{pg.url}: {m.text[:300]}"))
                for name, step in [("players", check_players), ("season switch", check_season_switch), ("slow answers", check_slow_answers), ("compare", check_compare), ("explore", check_explore),
                                   ("teams", check_teams), ("other pages", check_other_pages)]:
                    print(f"- {pass_name}: {name}")
                    try:
                        step(page, base)
                    except Exception as e:                        # a missing element or a timeout is a failure too
                        failures.append(f"{pass_name} {name}: {type(e).__name__}: {str(e).splitlines()[0][:200]}")
                        print(f"  [FAIL] {name}: {type(e).__name__}: {str(e).splitlines()[0][:200]}")
                ctx.close()
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
