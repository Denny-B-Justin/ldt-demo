"""
gunicorn.conf.py
================
Production server configuration for the Local Development Tracker.

Use it explicitly:

    gunicorn -c gunicorn.conf.py app:server

Posit Connect runs its own launcher and may ignore this file; the settings
that matter there (``WEB_CONCURRENCY`` and friends) are read from env vars, so
set those in the content's **Vars** pane. The app is also self-sufficient
without this file -- ``datastore.ensure_warm_started()`` runs from a plain
``python app.py`` too.

Key choices
-----------
* **Threads, not just processes.** Every Databricks call and cache read is
  I/O-bound and releases the GIL while it waits, so a handful of threads per
  worker lets one slow request stop blocking every other user -- which was the
  "site goes unresponsive" symptom.
* **preload_app + post_fork warm.** The app module (and its large constant
  tables) is imported once before forking; each worker then starts its own
  background data warm, because threads do not survive ``fork()``.
"""

from __future__ import annotations

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8050')}"

workers = int(os.environ.get("WEB_CONCURRENCY", "3"))
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", "4"))

# Databricks warm reads can be slow on a cold serverless warehouse; give them
# room before the worker is killed.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
graceful_timeout = 30
keepalive = 5

preload_app = True
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "2000"))
max_requests_jitter = 200

accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LDT_LOG_LEVEL", "info").lower()


def post_fork(server, worker):  # noqa: ANN001, D401 - gunicorn hook signature
    """Each worker process starts its own background data warm."""
    try:
        import datastore

        datastore.ensure_warm_started()
    except Exception as exc:  # noqa: BLE001
        worker.log.warning("post_fork datastore warm kickoff failed: %s", exc)
