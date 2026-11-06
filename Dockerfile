# Container build for Hugging Face Spaces (free CPU Space: 2 vCPU / 16 GB RAM,
# sleeps only after ~48 h idle) -- far more headroom than Render's free tier
# (0.1 CPU / 512 MB, sleeps after 15 min). See deploy/HOSTING.md.
FROM python:3.11-slim

# Spaces run the container as uid 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH \
    MPLCONFIGDIR=/home/user/.mpl PYTHONUNBUFFERED=1
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .
# The parquet is not in git: download + checksum-verify the release asset
# data/DATA_VERSION points at (same step Render's build runs).
RUN python scraping/data_release.py fetch

ENV FLASK_DEBUG=0
EXPOSE 7860
# 2 workers x 4 threads: the Space has 2 vCPUs and plenty of RAM, so the
# 1-worker limit that Render's 512 MB needs does not apply here.
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:7860", "--workers", "2", "--threads", "4", "--timeout", "120", "--max-requests", "500", "--max-requests-jitter", "50"]
