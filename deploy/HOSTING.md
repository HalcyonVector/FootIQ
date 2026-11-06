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

## Better free host: Hugging Face Spaces (Docker)
A free CPU Space gives 2 vCPU / 16 GB RAM (20x the CPU, 30x the memory of Render
free) and only sleeps after ~48 h without a visitor. No card needed.

1. Create an account and a **new Space** at huggingface.co/new-space: SDK = Docker, hardware = CPU basic (free).
2. Create an access token with write access (Settings -> Access Tokens).
3. From this repo:
   ```bash
   deploy/push_to_hf.sh https://<hf-user>:<token>@huggingface.co/spaces/<hf-user>/<space>
   ```
4. The Space builds the `Dockerfile`, which downloads the data release
   (`data/DATA_VERSION`) and starts gunicorn on port 7860. Your site is at
   `https://<hf-user>-<space>.hf.space`.

Re-run step 3 after each push to deploy a new version. Render keeps working
unchanged (`render.yaml`), so you can run both and switch when you're happy.
