"""Gunicorn settings (auto-loaded from the working directory). Used by Render's start command."""

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# One process so the LocMem cache and throttle counters are shared by every request (set
# REDIS_URL to scale out). Threads cover the I/O-bound upstream calls.
workers = 1
worker_class = "gthread"
threads = 8

# A cold /plan or /heatmap waits on several upstream calls (10 s timeout + 1 retry each).
timeout = 60
graceful_timeout = 30

accesslog = "-"
errorlog = "-"
