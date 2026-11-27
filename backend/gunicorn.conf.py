"""Gunicorn settings. Command-line flags in deploy/gunicorn.service take precedence."""

import multiprocessing
import os

bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:8000")
# Threaded workers: a slow outbound call (the assistant waits up to 25 s for an AI provider) holds one
# thread, not a whole worker, so the rest of the site stays responsive.
worker_class = "gthread"
workers = int(os.environ.get("GUNICORN_WORKERS", min(3, multiprocessing.cpu_count() * 2 + 1)))
threads = int(os.environ.get("GUNICORN_THREADS", 2))
timeout = 60
graceful_timeout = 30  # time workers get to finish requests after SIGTERM
keepalive = 5
max_requests = 1000  # recycle workers to bound memory growth on small instances
max_requests_jitter = 200  # spread restarts so workers never recycle at the same moment
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
forwarded_allow_ips = "127.0.0.1"
