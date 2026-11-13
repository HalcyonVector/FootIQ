"""
Builds site/: the static front end that Vercel serves (see deploy/HOSTING.md).

Why: the Flask app on Render's free tier sleeps and takes 20+ seconds to wake. Vercel serves
static files from its edge and never sleeps, so the pages, the home-page cards, the coverage
table and player SEARCH are answered from there instantly; every other /api/ call is
forwarded to Render (vercel.json rewrite), which starts waking the moment a visitor lands.

    py -3 deploy/build_static.py

Output (committed, so Vercel needs no build step):
    site/*.html            the pages, rendered from the Jinja templates (no data needed)
    site/static/           the app's CSS and JS, unchanged
    site/data/*.json       search index, home-page facts, coverage, leagues
    site/vercel.json       clean URLs, the /api rewrite, cache headers

The shim that answers those calls in the browser is static/js/static-shim.js.
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SITE = ROOT / "site"
BACKEND = "https://footiq.onrender.com"
PAGES = {"index": "/", "player": "/player", "compare": "/compare", "league": "/league", "team": "/team",
         "scout": "/scout", "explore": "/explore", "coverage": "/coverage"}
HEAD_INJECT = '<script>window.FOOTIQ_STATIC=true;</script><script src="/static/js/static-shim.js"></script>'


def build_pages() -> None:
    import app as flask_app
    flask_app._ensure_warm_started = lambda: None          # rendering pages needs no data, so don't load any
    client = flask_app.app.test_client()
    for name, route in PAGES.items():
        html = client.get(route).get_data(as_text=True)
        assert "<head>" in html, route
        html = html.replace("<head>", "<head>" + HEAD_INJECT, 1)
        (SITE / f"{name}.html").write_text(html, encoding="utf-8")


def build_search_index(df) -> dict:
    """Same rows and fields as core/advanced/lookup.py's index, with the repeated strings
    (team, league, season, position) replaced by positions in small tables."""
    from core.advanced.lookup import _SEARCH_COLS, _clean_age, _clean_minutes, _clean_position, _search_index
    from core.media import _MANUAL_TRANSLATE
    _search_index()
    tables = {k: {} for k in ("team", "league", "season", "position")}

    def idx(kind, value):
        t = tables[kind]
        return t.setdefault(value, len(t))

    rows = []
    for t in zip(*(df[c].tolist() for c in _SEARCH_COLS)):
        if not isinstance(t[0], str):
            continue
        norm, pid, name, team, league, season, pos, mins, age = t
        rows.append([norm, int(pid), name, idx("team", team), idx("league", league), idx("season", season),
                     idx("position", _clean_position(pos)), _clean_minutes(mins), _clean_age(age)])
    return {"translate": {chr(k): v for k, v in _MANUAL_TRANSLATE.items()},
            **{k: list(v) for k, v in tables.items()}, "rows": rows}


def build_data() -> None:
    from core.advanced import extras, lookup, store
    import app as flask_app
    df = store.get_advanced_df()
    lookup.build_search_index()
    data = SITE / "data"
    data.mkdir(parents=True, exist_ok=True)
    dump = lambda name, obj: (data / f"{name}.json").write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    dump("search-index", build_search_index(df))
    facts = flask_app._hub_facts()
    dump("hub", {"facts": facts, "players": [extras.hub_player(i) for i in range(len(facts["featured"]))]})
    dump("coverage", {"rows": extras.coverage(), "excluded": flask_app.EXCLUDED_COMPETITIONS})
    dump("leagues", flask_app.LEAGUES)


def write_config() -> None:
    cfg = {
        "cleanUrls": True,
        "trailingSlash": False,
        "rewrites": [{"source": "/api/:path*", "destination": f"{BACKEND}/api/:path*"}],
        "headers": [
            {"source": "/static/(.*)", "headers": [{"key": "Cache-Control", "value": "public, max-age=300, must-revalidate"}]},
            {"source": "/data/(.*)", "headers": [{"key": "Cache-Control", "value": "public, max-age=3600, must-revalidate"}]},
        ],
    }
    (SITE / "vercel.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir()
    shutil.copytree(ROOT / "static", SITE / "static")
    build_pages()
    build_data()
    write_config()
    size = sum(f.stat().st_size for f in SITE.rglob("*") if f.is_file())
    print(f"Built {SITE} ({size / 1e6:.1f} MB, {len(list(SITE.rglob('*.html')))} pages)")


if __name__ == "__main__":
    main()
