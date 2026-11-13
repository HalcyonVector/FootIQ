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
- **Spins down after 15 minutes idle**, so the first visitor pays the whole boot.
  `.github/workflows/keep-warm.yml` keeps it awake 08:00-18:00 UTC (about 310 of the 750
  instance-hours a month, a pool shared with the other projects) with one looping job per
  trigger, because GitHub drops most runs of a `*/10` schedule. Outside that window the
  first visit still pays the boot.

## Why not Vercel
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
