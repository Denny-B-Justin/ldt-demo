# Local Development Tracker (Dash edition)

A Python/Dash re-implementation of the Local Development Tracker (LDT) - a
public, municipality-level analytics application for comparing local
development conditions (Prosperity, Infrastructure, Livability - "PIL"),
reading score drivers, tracking local planning-strategy documents, and
connecting evidence to public investment decisions across Nepal, Serbia,
and Zambia.

This app is a from-scratch migration of an existing Next.js/React
application to Dash, built to be hosted on **Posit Connect**. Its data
layer reads live from Databricks Unity Catalog (see section 3).

---

## 1. What's in this repo

| File | One-liner |
|---|---|
| `app.py` | Main Dash application: page layouts for every route, the router, and every callback (theme, navigation, analytics filters, strategy-inventory filters, CSV export). |
| `utils.py` | Toolkit of reusable pieces: Plotly figure builders (choropleth map, 2D/3D scatter, waterfall, bar charts) and reusable Dash UI components (header, footer, cards, badges, buttons). |
| `constants.py` | All static content and configuration: navigation, design tokens/colors, country metadata, and the full text content of the About, Methodology, Roadmap, Resources, and Release Notes pages. |
| `queries.py` | The data-access layer: `QueryService` (cached Databricks SQL executor), the Unity Catalog -> `analytics-data.json`-shape assembler, boundary geometry decode, the documents-Volume strategy inventory, plus every pure data-shaping function (score averages, province summaries, waterfall/driver calculations, strategy-inventory readiness logic). The assemblers are pluggable providers -- `datastore.py` swaps in cached versions so requests never call them directly. |
| `datastore.py` | The request-safe data layer. Runs the Databricks assemblers **once**, off the request path, into gzipped-JSON artifacts on disk; every page then renders from a local dict lookup. Background `warm()`, staleness scheduling, `/healthz` + refresh support. See section 3. |
| `memo.py` | Small bounded LRU memo for deterministic-within-a-release results (assembled tab payloads, built figures, rendered tab content). Flushed automatically whenever `datastore` lands fresh data. |
| `gunicorn.conf.py` | Production server config: threaded workers (so one slow request can't freeze the app), `preload_app`, per-worker background warm. |
| `scripts/build_snapshot.py` | Builds the shipped data snapshot (`assets/data/_snapshot/`) before a deploy, so the first request after deploy is instant. |
| `assets/styles.css` | The full design system (CSS custom properties for light/dark themes) plus hand-written component classes that reproduce the original Tailwind-based UI (Dash has no Tailwind build step, so this is a plain CSS port). Dash auto-loads everything in `assets/`. |
| `assets/*.png`, `assets/*.webp` | Logos and figures used across the site (header/footer logos, About/Methodology page figures, partner logos). Referenced from Python with `/assets/<file>` (Dash's `get_asset_url` convention). |
| `assets/data/<country>/*.json`, `*.geojson` | Bundled analytics snapshots and municipality boundary files per country - the offline fallback data source (see Section 3). |
| `README.md` | This file. |
| `.env.sample` | Template for environment variables; copy to `.env` for local dev. |
| `scripts/introspect_databricks.py` | One-shot Unity Catalog / Volume schema dump used to verify/adjust the per-country column config. |
| `requirements.txt` | Python dependencies (Python 3.9-compatible pins). |

---

## 2. Architecture

### 2.1 Application shape

This is a **single Dash app with client-side routing**, not Dash's
multi-page (`pages/`) framework, so the whole app ships as the 8 files
listed above rather than a `pages/` directory tree.

```
dcc.Location(id="url")              <- browser URL, watched by the router
        |
        v
render_page_content(pathname)       <- single callback in app.py
        |
        +--> build_route_content()  <- maps a pathname to a page-builder
        |         function (render_home, render_about, render_analytics, ...)
        |
        +--> utils.app_header() / utils.app_footer()
```

Every route from the original Next.js `src/app/` tree has a matching
Python function in `app.py`:

| Route | Builder function |
|---|---|
| `/` | `render_home()` |
| `/about` | `render_about()` |
| `/methodology` | `render_methodology()` |
| `/roadmap` | `render_roadmap()` |
| `/resources` | `render_resources()` |
| `/release-notes` | `render_release_notes()` |
| `/{nepal\|serbia\|zambia}` | `render_country_landing(slug)` |
| `/{country}/analytics` | `render_analytics(slug)` |
| `/{serbia\|zambia}/strategy-inventory` | `render_strategy_inventory(slug)` |
| anything else | `render_not_found()` |

### 2.2 Interactivity (callbacks)

- **Theme toggle** - a header button flips a `dcc.Store(id="theme-store",
  storage_type="local")` between `light`/`dark`; a clientside callback
  applies `data-theme` to `<html>`, which `assets/styles.css` uses to swap
  CSS custom properties. The store is `localStorage`-backed so the choice
  persists across visits.
- **Mobile navigation** - a clientside callback toggles a `hidden` class on
  the slide-down nav panel.
- **Home country selector** - a dropdown + button pushes `/{slug}` onto
  `dcc.Location`, taking the user to that country's landing page.
- **Analytics filters** (`/{country}/analytics`) - year, province/district,
  municipality, and metric dropdowns plus a `dcc.Tabs` control (Map / 2D
  Scatter / 3D Scatter / Score Drivers). Changing any filter or tab
  re-runs `queries.get_analytics_page_data(...)` and rebuilds only the
  active tab's chart, mirroring the original React app's
  filter-driven `AnalyticsShell`.
- **CSV export** - a per-country download button (Dash `ALL` pattern
  matching) streams a CSV of the current municipality metrics table via
  `dcc.Download`.
- **Strategy inventory filters** (`/{serbia,zambia}/strategy-inventory`) -
  search box + readiness/document-type/translation-status dropdowns
  recompute the summary cards, the two bar charts, and the results table
  in one callback.

### 2.3 Design system

`assets/styles.css` is a 1:1 port of the CSS custom properties from the
original app's `globals.css` (light theme in `:root`, dark theme under
`html[data-theme="dark"]`), plus hand-written classes for every
component pattern that used to be Tailwind utility classes: the dark GPB
header/footer chrome, hero sections, stat cards, capability cards, figure
cards, tables, badges, filter bars, tabs, and the roadmap timeline. Dash
serves everything under `assets/` automatically, so no build step is
required.

---

## 3. Data sources and the database

### 3.0 How data flows (and when queries run)

Unity Catalog data changes only on a **release cadence**, so the app treats
the assembled datasets as build artifacts rather than something to fetch per
request.

```
                         BUILD / BACKGROUND (never on a request)
  Databricks UC ──► queries._assemble_* ──► datastore.warm() ──► .ldt_cache/*.json.gz
       ▲                                          ▲                     │
       │                                          │                     ▼
  scripts/build_snapshot.py            POST /ldt/admin/refresh    manifest.json
  (pre-deploy, writes                  + auto warm when the
   assets/data/_snapshot/)             newest artifact is stale

                         REQUEST PATH (pure local reads)
  browser ──► router callback ──► render_*() ──► datastore.<accessor>()
                                                    │
                    in-process memo ◄── .ldt_cache ◄── assets/data/_snapshot
                                                    ◄── assets/data/<country>/  (legacy bundled)
```

| Page / interaction | What runs on the request | Databricks? |
|---|---|---|
| Home, About, Methodology, Roadmap, Resources, Release Notes | Static `constants.py`; Home adds a 3-number lookup from `datastore.home_summary()` | Never |
| Country landing page | `datastore.analytics_dataset()` dict lookup + pure shaping | Never |
| Analytics page — **first paint** | Filter/selection metadata only (`get_analytics_page_data(..., sections=set())`) | Never |
| Analytics page — a tab / filter change | Builds **only that tab's** data + figure, memoised by selection; wrapped in `dcc.Loading` | Never |
| Strategy inventory | Serves the artifact `warm()` produced; shows a "not loaded yet" state until it exists | Never on the request |
| `warm()` / refresh / `build_snapshot.py` | Full `SELECT *` reads + assembly for every country | **Yes** — background only |

The only wait a user ever sees is a chart building after they pick something to
visualise, and only the first time that exact selection is chosen per worker.

### 3.1 Databricks and the artifact cache

The datasets **originate** in Databricks Unity Catalog (schema
`prd_mega.sgpbpi163`) via an OAuth service principal. The four `DATABRICKS_*`
environment variables are still required — `queries.py` raises
`EnvironmentError` at import without them.

Artifacts are resolved in this order, per country:

1. `LDT_CACHE_DIR` (default `./.ldt_cache`) — writable, refreshed at runtime.
2. `LDT_SNAPSHOT_DIR` (default `assets/data/_snapshot/`) — read-only, shipped
   with the deploy by `scripts/build_snapshot.py`.
3. `assets/data/<country>/analytics-data.json` + `municipalities.geojson` —
   the legacy bundled files, now a genuine last-resort fallback.

Serving from 2 or 3 also schedules a background `warm()` so the writable cache
catches up. `warm()` runs when the newest artifact is older than
`LDT_DATA_MAX_AGE_SECONDS` (default 12h), on process start, or on demand via
`POST /ldt/admin/refresh` (guard with `LDT_REFRESH_TOKEN`; point a Posit
Connect scheduled job at it after each data release).

### 3.2 Unity Catalog tables

Per country (`NPL` / `SRB` / `ZMB`):

| Table | Purpose |
|---|---|
| `GPBP_LDT_<ISO3>_admin_2` | Indicator panel - one row per admin-2 unit per year, with the raw indicator columns and context columns (`Population`, `Total Land Area (km2)`, road/rail lengths and risk-km). |
| `GPBP_LDT_<ISO3>_scores_admin_2` | 0-100 percentile score panel - one row per admin-2 unit per year, with component score columns and the three pillar scores (`Infrastructure Score`, `Livability Score`, `Prosperity Score`). |
| `ldt_boundaries_admin2_<country>` | Admin-2 geometry for the choropleth (WKT / WKB / GeoJSON - auto-detected). `admin0` / `admin1` boundary tables exist but are not used yet. |

The Strategy Inventory page (Serbia / Zambia) is built by listing the
planning-documents Volume at `LDT_DOCUMENTS_VOLUME` (default
`/Volumes/prd_mega/sgpbpi163/vgpbpi163/LDT/Local Development Plans`) via the
Databricks SDK Files API and deriving one record per document file.

Static indicator metadata (labels, descriptions, direction, pillar,
sources - identical across all three countries) ships in
`assets/data/indicator_definitions.json` rather than a table.

### 3.3 How the dataset is assembled

`queries.py` mirrors, function for function,
`wb-ldt-app/scripts/lib/nepal-data.mjs` - the Node script that generated
the JSON snapshots the app used before this migration - but reads
DataFrames from `QueryService.execute_query()` instead of CSV files:

- `QueryService` is a thread-safe singleton with an in-memory TTL cache
  (`QUERY_CACHE_TTL_SECONDS`, default 300s).
- `get_analytics_dataset(code)` queries the admin + scores tables, maps the
  raw columns to canonical metric ids (`constants.ADMIN_CANONICAL_MAPPINGS`
  / `SCORE_CANONICAL_MAPPINGS`), joins scores to admin rows on
  `Year::Province::District::Municipality`, and returns the same dict shape
  the old `analytics-data.json` had - so every downstream pure function is
  unchanged.
- `load_map_feature_collection(code)` queries the boundary table, decodes
  and simplifies each geometry with `shapely`, merges multi-row geometries
  per unit, and emits a GeoJSON `FeatureCollection` keyed by `compositeKey`.

Column names are resolved **tolerantly** (case- and punctuation-insensitive)
against `constants.COUNTRY_DATA_SOURCES`, and every fetch is logged, e.g.:

```
INFO | queries | Assembling ZMB analytics dataset from prd_mega.sgpbpi163 (gpbp_ldt_zmb_admin_2 + gpbp_ldt_zmb_scores_admin_2)
INFO | queries | Databricks query returned 580 rows x 34 cols in 1.21s: SELECT * FROM `prd_mega`.`sgpbpi163`.`gpbp_ldt_zmb_admin_2`
INFO | queries | ZMB boundary columns resolved: municipality=NAM_2 district=NAM_1 province=NAM_1 geometry=geometry_wkt
```

If a column cannot be resolved by the tolerant match, run
`python scripts/introspect_databricks.py` (dumps `DESCRIBE` + sample rows
for all 15 tables and walks the Volume) and correct the exact names in the
relevant `constants.COUNTRY_DATA_SOURCES` block.

### 3.4 Where each page's data comes from

All reads below resolve from the local artifact cache (section 3.1), never a
live query. See the flow table in section 3.0 for what actually executes.

| Page | Data source |
|---|---|
| Home | `datastore.home_summary()` — 3 pre-computed numbers. |
| About, Methodology, Roadmap, Resources, Release Notes | 100% static content from `constants.py`. |
| Country landing page | `queries.load_country_dataset()` (→ `datastore.analytics_dataset()`) + pure shaping. |
| Country analytics page | `queries.get_analytics_page_data(..., sections=...)` — only the requested tab's blocks, memoised per selection. |
| Strategy inventory page | `datastore.strategy_inventory()` — the artifact from `warm()`. |

### 3.5 Tests and offline development

`pytest` (`pip install -r requirements-dev.txt`) runs fully offline - the
suite monkeypatches `queries.execute_query` with synthetic DataFrames whose
column names match the source CSVs, so the assembler's expected output is
known exactly. `tests/test_datastore.py` covers artifact resolution, `warm()`,
and that the accessors never touch the query path.

For offline UI work without Databricks, the bundled
`assets/data/<country>/analytics-data.json` + `municipalities.geojson` files
are used automatically as the last-resort fallback (set `LDT_DISABLE_BG_WARM=1`
to stop the futile background warm attempts).

### 3.6 What was intentionally simplified

1. **The multi-stage AI Planning Brief pipeline** is not reimplemented.
2. **Per-municipality plan availability** - the country-page "plan source
   availability" disclosure groups units by province but does not yet mark
   individual availability from the Volume listing (see
   `build_plan_availability_groups()` in `app.py`).

Everything else - every page, chart type, filter, static content, the
design system, dark mode, and the CSV export - is fully implemented.

---

## 4. Running locally

```bash
# 1. Create and activate a virtual environment (Python 3.9+)
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment variables (REQUIRED - the app is Databricks-only)
cp .env.sample .env
# fill in DATABRICKS_SERVER_HOSTNAME, DATABRICKS_HTTP_PATH,
# DATABRICKS_CLIENT_ID, DATABRICKS_CLIENT_SECRET (service principal).

# 4. (optional) build a fresh data snapshot to ship with the app
python scripts/build_snapshot.py     # writes assets/data/_snapshot/

# 5. Run the app
python app.py                        # dev server
gunicorn -c gunicorn.conf.py app:server   # production-like
# -> Dash is running on http://127.0.0.1:8050/
```

On start the app renders immediately from the shipped snapshot (or the bundled
fallback) and kicks a **background** `warm()` to refresh `./.ldt_cache/` from
Databricks. Set `DASH_DEBUG=false` to run without hot reload, `PORT=<n>` to
change the port, and `LDT_DISABLE_BG_WARM=1` for pure offline UI work.

---

## 5. Deploying to Posit Connect

This app exposes a standard WSGI `server` object (`server = app.server` in
`app.py`), which is what Posit Connect's Python/Dash content type expects.

0. **Build the data snapshot first:** `python scripts/build_snapshot.py`, and
   include the resulting `assets/data/_snapshot/` in the bundle. This is what
   makes the first request after a deploy instant instead of waiting on the
   background warm.
1. In the Connect content folder, include: `app.py`, `utils.py`,
   `constants.py`, `queries.py`, `datastore.py`, `memo.py`,
   `gunicorn.conf.py`, `requirements.txt`, `scripts/`, and the `assets/`
   folder (with `data/`, including `_snapshot/`). Do not include `.env` - set
   environment variables through Connect's **Vars** pane instead. The
   deployment host must have network egress to the Databricks SQL warehouse.
2. Publish with `rsconnect-python`:

   ```bash
   pip install rsconnect-python
   rsconnect deploy dash . \
     --server https://<your-connect-server> \
     --api-key <your-api-key> \
     --entrypoint app:server
   ```

   (Or use the **Publish** button in the Connect-aware IDE extension /
   Posit Workbench, selecting this directory and confirming the `app:server`
   entrypoint.)
3. In the content's **Vars** settings on Connect, set the four
   `DATABRICKS_*` variables from `.env.sample` (required), plus
   `LDT_CATALOG` / `LDT_SCHEMA` / `LDT_DOCUMENTS_VOLUME` if they differ
   from the defaults. Also set:
   - `LDT_CACHE_DIR` to a **writable, persistent** path on the content
     (so refreshed artifacts survive between requests and restarts).
   - `LDT_REFRESH_TOKEN` to a secret, then add a Connect **scheduled job**
     that `POST`s to `https://<connect>/content/<guid>/ldt/admin/refresh?token=<secret>`
     shortly after each data release. (The app also self-refreshes every
     `LDT_DATA_MAX_AGE_SECONDS`.)
   - `WEB_CONCURRENCY` / `GUNICORN_THREADS` if the defaults (3 / 4) don't
     suit the instance size.
4. Confirm the **Access** setting matches your intended audience (this is
   a public-analytics-style app in its original form, but Connect lets
   you restrict it to specific users/groups if needed).

`/healthz` returns the data-layer status (artifact age, last warm result,
whether the cache dir is writable) — useful for a Connect health check.

---

## 6. Notes on fidelity

- Every page, section, and piece of copy from the original app's About,
  Methodology, Roadmap, Resources, and Release Notes pages is reproduced
  in `constants.py` (headings, body copy, tables, and footnotes included).
- All four analytics visualizations (choropleth map, 2D scatterplot, 3D
  scatterplot, score-driver waterfall) are rebuilt in Plotly using the
  same color logic, hover content, and highlighted-vs-peer-vs-other
  marker treatment as the original React/Plotly components.
- The dark GPB header/footer chrome, GPB Suite badge, and PIM-PAM footer
  branding plate are reproduced as closely as Dash + plain CSS allow.
- Because Dash's rendering model differs fundamentally from
  Next.js/React (server-rendered component tree + callback graph vs.
  client-side component state), some interaction details - in particular
  MapLibre's free-form pan/zoom map vs. Plotly's `Choroplethmap` trace -
  are functionally equivalent rather than pixel-identical.
