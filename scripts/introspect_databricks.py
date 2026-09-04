"""
introspect_databricks.py
========================
One-shot Unity Catalog / Volume introspection for the Local Development Tracker
migration (Supabase -> Databricks).

It connects with the same OAuth service-principal flow the app will use, then
dumps - for every table and volume the app needs - the exact column names,
types, a few sample rows, row counts, the distinct year values, and (for the
boundary tables) how geometry is encoded and in which CRS. It also walks the
planning-documents Volume so the strategy-inventory reader can be written
against the real folder/file layout.

Nothing here writes to Databricks. Output is printed to stdout *and* saved to
``scratchpad/databricks_introspection.txt`` next to this repo.

Usage
-----
    pip install databricks-sql-connector databricks-sdk python-dotenv
    # populate .env first (see .env.sample), then:
    python scripts/introspect_databricks.py

Then paste the contents of scratchpad/databricks_introspection.txt back so the
per-country config blocks in constants.py can be finalised.
"""

from __future__ import annotations

import os
import sys
import io
import json
import traceback
from contextlib import redirect_stdout
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - dotenv is optional
    print("(python-dotenv not installed; reading env vars from the shell only)")

from databricks import sql
from databricks.sdk.core import Config, oauth_service_principal


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

SERVER_HOSTNAME = os.getenv("DATABRICKS_SERVER_HOSTNAME")
HTTP_PATH = os.getenv("DATABRICKS_HTTP_PATH")
CLIENT_ID = os.getenv("DATABRICKS_CLIENT_ID")
CLIENT_SECRET = os.getenv("DATABRICKS_CLIENT_SECRET")

CATALOG = os.getenv("LDT_CATALOG", "prd_mega")
SCHEMA = os.getenv("LDT_SCHEMA", "sgpbpi163")
DOCUMENTS_VOLUME = os.getenv(
    "LDT_DOCUMENTS_VOLUME",
    "/Volumes/prd_mega/sgpbpi163/vgpbpi163/LDT/Local Development Plans",
)

_REQUIRED = {
    "DATABRICKS_SERVER_HOSTNAME": SERVER_HOSTNAME,
    "DATABRICKS_HTTP_PATH": HTTP_PATH,
    "DATABRICKS_CLIENT_ID": CLIENT_ID,
    "DATABRICKS_CLIENT_SECRET": CLIENT_SECRET,
}

# The 15 tables the app reads, grouped by role.
INDICATOR_TABLES = [
    "GPBP_LDT_NPL_admin_2",
    "GPBP_LDT_SRB_admin_2",
    "GPBP_LDT_ZMB_admin_2",
]
SCORE_TABLES = [
    "GPBP_LDT_NPL_scores_admin_2",
    "GPBP_LDT_SRB_scores_admin_2",
    "GPBP_LDT_ZMB_scores_admin_2",
]
BOUNDARY_TABLES = [
    "ldt_boundaries_admin0_nepal",
    "ldt_boundaries_admin1_nepal",
    "ldt_boundaries_admin2_nepal",
    "ldt_boundaries_admin0_serbia",
    "ldt_boundaries_admin1_serbia",
    "ldt_boundaries_admin2_serbia",
    "ldt_boundaries_admin0_zambia",
    "ldt_boundaries_admin1_zambia",
    "ldt_boundaries_admin2_zambia",
]

# Column names that might carry the observation year, tried in order.
YEAR_CANDIDATES = ["Year", "year", "YEAR", "release_year", "data_year"]

# Substrings that hint a column holds geometry.
GEOMETRY_HINTS = ("geom", "wkt", "wkb", "shape", "boundary", "polygon", "geojson")


# --------------------------------------------------------------------------
# Connection
# --------------------------------------------------------------------------

def credentials_provider():
    config = Config(
        host=f"https://{SERVER_HOSTNAME}",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
    )
    return oauth_service_principal(config)


def connect():
    return sql.connect(
        server_hostname=SERVER_HOSTNAME,
        http_path=HTTP_PATH,
        credentials_provider=credentials_provider,
    )


def fqtn(table: str) -> str:
    return f"`{CATALOG}`.`{SCHEMA}`.`{table}`"


def run(cursor, query: str):
    cursor.execute(query)
    rows = cursor.fetchall()
    columns = [d[0] for d in cursor.description] if cursor.description else []
    return columns, rows


def _truncate(value, limit: int = 120) -> str:
    text = "NULL" if value is None else str(value)
    text = text.replace("\n", " ")
    if len(text) > limit:
        return text[:limit] + f"... [{len(text)} chars]"
    return text


# --------------------------------------------------------------------------
# Probes
# --------------------------------------------------------------------------

def list_schema_tables(cursor) -> None:
    print(f"\n{'=' * 78}\nSHOW TABLES IN {CATALOG}.{SCHEMA}\n{'=' * 78}")
    try:
        _, rows = run(cursor, f"SHOW TABLES IN `{CATALOG}`.`{SCHEMA}`")
        for row in rows:
            print("  ", " | ".join(_truncate(v, 60) for v in row))
    except Exception as exc:  # noqa: BLE001
        print(f"  !! failed: {exc}")

    print(f"\n{'-' * 78}\nSHOW VOLUMES IN {CATALOG}.{SCHEMA}\n{'-' * 78}")
    try:
        _, rows = run(cursor, f"SHOW VOLUMES IN `{CATALOG}`.`{SCHEMA}`")
        for row in rows:
            print("  ", " | ".join(_truncate(v, 60) for v in row))
    except Exception as exc:  # noqa: BLE001
        print(f"  !! failed: {exc}")


def describe_table(cursor, table: str) -> list[str]:
    """Print schema + return the column-name list."""
    print(f"\n{'=' * 78}\nTABLE  {fqtn(table)}\n{'=' * 78}")
    column_names: list[str] = []
    try:
        cols, rows = run(cursor, f"DESCRIBE TABLE EXTENDED {fqtn(table)}")
        print("  -- columns --")
        for row in rows:
            record = dict(zip(cols, row))
            name = (record.get("col_name") or "").strip()
            dtype = (record.get("data_type") or "").strip()
            if not name or name.startswith("#"):
                if name.startswith("#"):
                    print(f"  {name} {dtype}".rstrip())
                continue
            column_names.append(name)
            print(f"    {name:<40} {dtype}")
    except Exception as exc:  # noqa: BLE001
        print(f"  !! DESCRIBE failed: {exc}")

    try:
        _, rows = run(cursor, f"SELECT count(*) FROM {fqtn(table)}")
        print(f"\n  row count: {rows[0][0]:,}")
    except Exception as exc:  # noqa: BLE001
        print(f"  !! count failed: {exc}")

    return column_names


def sample_rows(cursor, table: str, columns: list[str], geometry_cols: list[str]) -> None:
    """Print up to 3 sample rows, truncating geometry columns hard."""
    try:
        cols, rows = run(cursor, f"SELECT * FROM {fqtn(table)} LIMIT 3")
    except Exception as exc:  # noqa: BLE001
        print(f"  !! sample select failed: {exc}")
        return

    print("\n  -- sample rows --")
    for i, row in enumerate(rows):
        print(f"  row {i}:")
        for name, value in zip(cols, row):
            limit = 80 if name in geometry_cols else 160
            print(f"    {name:<40} = {_truncate(value, limit)}")


def probe_years(cursor, table: str, columns: list[str]) -> None:
    year_col = next((c for c in YEAR_CANDIDATES if c in columns), None)
    if not year_col:
        # case-insensitive retry
        lower = {c.lower(): c for c in columns}
        year_col = lower.get("year")
    if not year_col:
        print("\n  -- years -- (no year-like column found)")
        return
    try:
        _, rows = run(
            cursor,
            f"SELECT DISTINCT `{year_col}` FROM {fqtn(table)} ORDER BY `{year_col}`",
        )
        values = [r[0] for r in rows]
        print(f"\n  -- years -- column `{year_col}`: {values}")
    except Exception as exc:  # noqa: BLE001
        print(f"  !! distinct years failed: {exc}")


def probe_geometry(cursor, table: str, columns: list[str]) -> None:
    geometry_cols = [
        c for c in columns if any(hint in c.lower() for hint in GEOMETRY_HINTS)
    ]
    print(f"\n  -- geometry columns detected: {geometry_cols or 'NONE'}")
    for col in geometry_cols:
        try:
            _, rows = run(
                cursor,
                f"SELECT `{col}`, typeof(`{col}`) FROM {fqtn(table)} "
                f"WHERE `{col}` IS NOT NULL LIMIT 1",
            )
        except Exception as exc:  # noqa: BLE001
            print(f"    {col}: !! probe failed: {exc}")
            continue
        if not rows:
            print(f"    {col}: all NULL")
            continue
        raw, dtype = rows[0]
        text = str(raw)
        head = text[:60]
        if text.strip().startswith("{"):
            encoding = "geojson-string"
        elif text[:20].upper().lstrip().startswith(
            ("POLYGON", "MULTIPOLYGON", "POINT", "LINESTRING", "GEOMETRYCOLLECTION")
        ):
            encoding = "wkt-text"
        elif all(ch in "0123456789abcdefABCDEF" for ch in text[:32]) and len(text) > 32:
            encoding = "wkb-hex"
        elif isinstance(raw, (bytes, bytearray)):
            encoding = "wkb-binary"
        else:
            encoding = "unknown"
        print(f"    {col}: sql_type={dtype} guessed_encoding={encoding}")
        print(f"        head: {head!r}")

    # Coordinate-range hint for CRS (works for wkt-text only).
    for col in geometry_cols:
        try:
            _, rows = run(
                cursor,
                f"SELECT `{col}` FROM {fqtn(table)} WHERE `{col}` IS NOT NULL LIMIT 1",
            )
            if not rows:
                continue
            text = str(rows[0][0])
            import re

            nums = [float(x) for x in re.findall(r"-?\d+\.\d+", text)[:400]]
            if nums:
                xs = nums[0::2]
                ys = nums[1::2]
                print(
                    f"    {col}: coord ranges  x[{min(xs):.3f}, {max(xs):.3f}]  "
                    f"y[{min(ys):.3f}, {max(ys):.3f}]  "
                    f"(lat/lon degrees => EPSG:4326; large metres => projected)"
                )
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------
# Volume walk
# --------------------------------------------------------------------------

def walk_volume() -> None:
    print(f"\n{'=' * 78}\nVOLUME  {DOCUMENTS_VOLUME}\n{'=' * 78}")
    try:
        from databricks.sdk import WorkspaceClient
    except Exception as exc:  # noqa: BLE001
        print(f"  !! databricks-sdk unavailable: {exc}")
        return

    try:
        client = WorkspaceClient(
            host=f"https://{SERVER_HOSTNAME}",
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  !! WorkspaceClient init failed: {exc}")
        return

    total = {"dirs": 0, "files": 0}

    def _walk(path: str, depth: int) -> None:
        if depth > 4:
            print("    " * depth + "... (max depth reached)")
            return
        try:
            entries = list(client.files.list_directory_contents(path))
        except Exception as exc:  # noqa: BLE001
            print("  " * depth + f"!! cannot list {path}: {exc}")
            return
        entries.sort(key=lambda e: (not e.is_directory, (e.path or "").lower()))
        shown_files = 0
        for entry in entries:
            name = (entry.path or "").rstrip("/").split("/")[-1]
            if entry.is_directory:
                total["dirs"] += 1
                print("  " * depth + f"[dir]  {name}/")
                _walk(entry.path, depth + 1)
            else:
                total["files"] += 1
                shown_files += 1
                if shown_files <= 12:
                    size = getattr(entry, "file_size", None)
                    size_s = f"  ({size:,} bytes)" if isinstance(size, int) else ""
                    print("  " * depth + f"       {name}{size_s}")
                elif shown_files == 13:
                    print("  " * depth + "       ... (more files not shown)")

    _walk(DOCUMENTS_VOLUME, 1)
    print(f"\n  volume totals: {total['dirs']} dirs, {total['files']} files")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> int:
    missing = [k for k, v in _REQUIRED.items() if not v]
    if missing:
        print("Missing required environment variables:")
        for key in missing:
            print(f"  {key}")
        print("\nPopulate .env (see .env.sample) and re-run.")
        return 1

    print(f"Local Development Tracker - Databricks introspection")
    print(f"generated: {datetime.now(timezone.utc).isoformat()}")
    print(f"host     : {SERVER_HOSTNAME}")
    print(f"http_path: {HTTP_PATH}")
    print(f"catalog  : {CATALOG}")
    print(f"schema   : {SCHEMA}")
    print(f"volume   : {DOCUMENTS_VOLUME}")

    with connect() as conn:
        cursor = conn.cursor()

        list_schema_tables(cursor)

        for table in INDICATOR_TABLES + SCORE_TABLES:
            columns = describe_table(cursor, table)
            sample_rows(cursor, table, columns, geometry_cols=[])
            probe_years(cursor, table, columns)

        for table in BOUNDARY_TABLES:
            columns = describe_table(cursor, table)
            geometry_cols = [
                c for c in columns if any(h in c.lower() for h in GEOMETRY_HINTS)
            ]
            sample_rows(cursor, table, columns, geometry_cols=geometry_cols)
            probe_geometry(cursor, table, columns)

    walk_volume()

    print(f"\n{'=' * 78}\nDONE\n{'=' * 78}")
    return 0


if __name__ == "__main__":
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(repo_root, "scratchpad")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "databricks_introspection.txt")

    buffer = io.StringIO()
    exit_code = 0
    try:
        with redirect_stdout(buffer):
            exit_code = main()
    except Exception:  # noqa: BLE001
        buffer.write("\n\nUNHANDLED ERROR:\n")
        buffer.write(traceback.format_exc())
        exit_code = 2
    finally:
        text = buffer.getvalue()
        sys.stdout.write(text)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text)
        sys.stdout.write(f"\n\n(output also written to {out_path})\n")

    sys.exit(exit_code)
