"""Gunicorn settings. Command-line flags in deploy/gunicorn.service take precedence."""

import multiprocessing
import os

bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:8000")
workers = int(os.environ.get("GUNICORN_WORKERS", min(3, multiprocessing.cpu_count() * 2 + 1)))
threads = int(os.environ.get("GUNICORN_THREADS", 2))
worker_class = "gthread"
timeout = 60
graceful_timeout = 30  # time workers get to finish requests after SIGTERM
keepalive = 5
max_requests = 1000  # recycle workers to bound memory growth on small instances
max_requests_jitter = 100
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
forwarded_allow_ips = "127.0.0.1"
