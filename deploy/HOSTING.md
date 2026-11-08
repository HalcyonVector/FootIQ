# Hosting notes (free tiers only)

## Why the app is slow on Render's free tier
- **0.1 CPU and 512 MB RAM.** Importing pandas/pyarrow and warming the
  datasets takes a few seconds on a laptop and a minute or more there. Charts used to
  be rendered server-side with matplotlib (~3 s of CPU per Advanced Metrics tab); they
  are now drawn in the browser from small JSON specs, so that cost is gone.
- **Spins down after 15 minutes idle**, so the first visitor pays the whole boot.
  Keeping it awake costs instance-hours from a pool shared with the other projects
  (see `.github/workflows/keep-warm.yml`), so it's off by default.

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
