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
| `queries.py` | The data-access layer: `QueryService` (cached Databricks SQL executor), the Unity Catalog -> `analytics-data.json`-shape assembler, boundary geometry decode, the documents-Volume strategy inventory, plus every pure data-shaping function (score averages, province summaries, waterfall/driver calculations, strategy-inventory readiness logic). |
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

The app reads **every dataset live from Databricks Unity Catalog** (schema
`prd_mega.sgpbpi163`) through an OAuth service principal. There is **no
bundled-data fallback**: if the four `DATABRICKS_*` environment variables
are not set, `queries.py` raises `EnvironmentError` at import and the app
does not start.

### 3.1 Unity Catalog tables

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

### 3.2 How the dataset is assembled

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

### 3.3 Where each page's data comes from

| Page | Data source |
|---|---|
| Home | `queries.get_analytics_dataset()` per country, aggregated into global coverage stats. |
| About, Methodology, Roadmap, Resources, Release Notes | 100% static content from `constants.py` - no database calls. |
| Country landing page | `queries.load_country_dataset()` + `queries.build_country_home_model()` + `queries.get_country_landing_actions()` / `get_plan_availability_disclosure()`. |
| Country analytics page | `queries.get_analytics_page_data()` - assembles filters, selected municipality, map features, scatter points, score-driver rows, and waterfall groups. |
| Strategy inventory page | `queries.get_strategy_inventory_dataset()` (documents Volume listing) + `queries.get_strategy_inventory_summary()` / `get_readiness_category()`. |

### 3.4 Tests and offline development

`pytest` (`pip install -r requirements-dev.txt`) runs fully offline - the
suite monkeypatches `queries.execute_query` with synthetic DataFrames whose
column names match the source CSVs, so the assembler's expected output is
known exactly. The bundled `assets/data/<country>/*.json` snapshots are kept
only as a reference for those fixtures; nothing reads them at runtime.

### 3.5 What was intentionally simplified

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

# 4. Run the app
python app.py
# -> Dash is running on http://127.0.0.1:8050/
```

Set `DASH_DEBUG=false` in `.env` (or your shell) to run without hot
reload, and `PORT=<n>` to change the port.

---

## 5. Deploying to Posit Connect

This app exposes a standard WSGI `server` object (`server = app.server` in
`app.py`), which is what Posit Connect's Python/Dash content type expects.

1. In the Connect content folder, include: `app.py`, `utils.py`,
   `constants.py`, `queries.py`, `requirements.txt`, and the `assets/`
   folder (with its `data/` subfolder, which holds
   `indicator_definitions.json`). Do not include `.env` - set environment
   variables through Connect's **Vars** pane instead. The deployment host
   must have network egress to the Databricks SQL warehouse.
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
   from the defaults.
4. Confirm the **Access** setting matches your intended audience (this is
   a public-analytics-style app in its original form, but Connect lets
   you restrict it to specific users/groups if needed).

No server-side build step is required beyond `pip install -r
requirements.txt` - Connect handles that automatically from the manifest
it generates during deploy.

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
