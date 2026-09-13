"""
build_snapshot.py
=================
Build the shipped data snapshot for the Local Development Tracker.

Run this **before every deploy that should carry fresh data**:

    python scripts/build_snapshot.py

It connects to Databricks (needs the four ``DATABRICKS_*`` env vars, exactly
like the app), assembles every country's analytics dataset, boundary GeoJSON
and strategy inventory, and writes them as gzipped-JSON artifacts into
``assets/data/_snapshot/`` together with a ``manifest.json``.

At runtime ``datastore.py`` resolves artifacts from the writable cache dir
first, then this snapshot, then the legacy bundled per-country files. So the
snapshot is what makes the first request after a fresh deploy instant -- the
background warm then refreshes the writable cache in place.

Commit the regenerated ``assets/data/_snapshot/`` (or include it in the
rsconnect bundle) so the deployment ships with it.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level="INFO", format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("build_snapshot")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=None,
        help="Output directory (default: assets/data/_snapshot).",
    )
    args = parser.parse_args()

    import datastore  # imports queries -> enforces the DATABRICKS_* env guard

    if args.out:
        datastore.CACHE_DIR = args.out
    else:
        datastore.CACHE_DIR = datastore.SNAPSHOT_DIR

    os.makedirs(datastore.CACHE_DIR, exist_ok=True)
    logger.info("Building snapshot into %s", datastore.CACHE_DIR)

    manifest = datastore.warm(force=True)

    logger.info("Snapshot complete: %s", manifest)
    for name in sorted(os.listdir(datastore.CACHE_DIR)):
        path = os.path.join(datastore.CACHE_DIR, name)
        logger.info("  %-28s %8.1f KiB", name, os.path.getsize(path) / 1024)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
