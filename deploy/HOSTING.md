# Hosting notes (free tiers only)

## Why the app is slow on Render's free tier
- **0.1 CPU and 512 MB RAM.** The container is CPU-throttled in nearly every scheduling
  period (`/api/health?detail=1` shows `cpu_stat`: about 219 of 222 periods throttled in one
  boot), so wall-clock time is roughly ten times CPU time. Importing pandas/pyarrow and
  loading the data is about 3 CPU-seconds, which is a few seconds on a laptop and 10 to 25
  seconds there. Charts used to be rendered server-side with matplotlib (~3 s of CPU per
  Advanced Metrics tab); they are now drawn in the browser from small JSON specs.
- **Start-up is trimmed to what a request needs.** The data gate opens once the player table
  and the search index are loaded (`ready` in `/api/health?detail=1`); the link-up table and
  the per-category dataset handles load afterwards. `requests` is imported lazily.
- **Spins down after 15 minutes idle**, so the first visitor pays the whole boot. The service
  (`https://footiq-syqc.onrender.com`) lives in a Render workspace of its own, whose 750 free
  instance-hours a month cover running all the time (about 744 in a 31-day month), so it is
  kept awake around the clock: an external monitor (UptimeRobot, every 5 minutes, on
  `/api/health`) as the main pinger, and `.github/workflows/keep-warm.yml` as a backup (one
  looping job per trigger, five triggers a day, because GitHub drops or delays most scheduled runs).
- **Build minutes.** The free workspace has 500 build minutes a month and every build downloads the
  dataset, so `render.yaml` has a build filter: pushes that only change `site/`, `static/`, docs,
  tests or the README do not rebuild the server.

## Static front end on Vercel (what visitors hit)
The Flask app on Render sleeps and takes 20+ seconds to wake, so `site/` holds a static copy of the
pages that Vercel's CDN serves instantly. In the browser, `static/js/static-shim.js` answers player
search (an index of every player-season, the same ranking as the server), the home-page cards, the
coverage table and the league list from small JSON files; every other `/api/` call is forwarded to
Render by the rewrite in `site/vercel.json`, and one background call to `/api/health` is sent as soon
as a page opens, so Render is already waking while the visitor reads and types.

Update it whenever templates, `static/`, the data or the featured players change:

    py -3 deploy/build_static.py          # rebuilds site/ (keeps the .vercel link)
    git add site && git commit && git push   # Vercel publishes it

The Vercel project is `footiq` (production alias https://footiq-app.vercel.app). It is linked to this
GitHub repo with **Root Directory = `site`**, so every push to `main` publishes `site/` (no build step;
the files are already built and committed). Without that setting Vercel would publish the repo root,
which has no index page, and every URL would return 404 (this happened once on 2026-11-19). Preview URLs of a
deployment are protected by Vercel login; the production alias is public. Commit `site/` too, since
it is the source of what is deployed.

## Why Vercel cannot host the data server itself
Vercel's free functions are serverless with a ~250 MB unzipped bundle limit. This app
needs pandas + pyarrow (~100 MB) *and* ~265 MB of data, and a function
that cold-starts per request would re-import all of it each time. It doesn't fit.

## Hugging Face Spaces: NOT free any more
Docker Spaces (and CPU Gradio Spaces) now require a paid HF plan; free accounts only get
Static Spaces and ZeroGPU Gradio. The `Dockerfile` and `.dockerignore` are kept only because the same container works on any host that
runs Docker, but there is currently no free HF route. (Checked Nov 2026.)

## What to do instead (free tier only)
Stay on Render. The matplotlib/mplsoccer imports and server-side chart rendering are gone,
so each request is far cheaper than when this page was written. The remaining cost is the
cold start after 15 idle minutes (pandas/pyarrow + warming the datasets).

## Checking the live site

    py -3 deploy/live_check.py

Wakes the Render app, waits for it to load its data, then checks health and memory, the home page, search, a player's advanced stats and the link-up list. Exits 1 on any failure.

## Chart check before each deploy

    py -3 -X utf8 deploy/chart_check.py                          # own copy of the app on port 5099
    py -3 -X utf8 deploy/chart_check.py https://footiq-app.vercel.app

Draws every chart in headless Chrome (Playwright, using the installed Chrome) and exits 1 if any chart fails to draw, a request ends in an error card or a page throws. A second pass at phone size also fails on sideways scrolling or chart text under 8px. Both passes also scroll the long pages and fail if a card stays hidden on screen. `--phone-only` or `--desktop-only` runs one pass. Exit 2 means it could not run (no Playwright or Chrome), which never blocks anything.

- `.githooks/pre-push` runs it when a push to `main` touches `static/`, `templates/`, `site/`, `core/` or `app.py`. Enable it once per clone: `git config core.hooksPath .githooks`.
- `scraping/auto_update.py` runs it after rebuilding `site/` and before committing; on failure it does not push, so the live site keeps last week's pointer. It sets `FOOTIQ_CHARTS_CHECKED=1` so the hook does not run it twice.
