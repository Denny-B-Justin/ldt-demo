# Local Development Tracker (Dash edition)

A Python/Dash re-implementation of the Local Development Tracker (LDT) - a
public, municipality-level analytics application for comparing local
development conditions (Prosperity, Infrastructure, Livability - "PIL"),
reading score drivers, tracking local planning-strategy documents, and
connecting evidence to public investment decisions across Nepal, Serbia,
and Zambia.

This app is a from-scratch migration of an existing Next.js/React/Supabase
application to Dash, built to be hosted on **Posit Connect**.

---

## 1. What's in this repo

| File | One-liner |
|---|---|
| `app.py` | Main Dash application: page layouts for every route, the router, and every callback (theme, navigation, analytics filters, strategy-inventory filters, CSV export). |
| `utils.py` | Toolkit of reusable pieces: Plotly figure builders (choropleth map, 2D/3D scatter, waterfall, bar charts) and reusable Dash UI components (header, footer, cards, badges, buttons). |
| `constants.py` | All static content and configuration: navigation, design tokens/colors, country metadata, and the full text content of the About, Methodology, Roadmap, Resources, and Release Notes pages. |
| `queries.py` | The data-access layer: Supabase reads (when configured) with a transparent fallback to bundled JSON snapshots, plus every pure data-shaping function (score averages, province summaries, waterfall/driver calculations, strategy-inventory readiness logic). |
| `assets/styles.css` | The full design system (CSS custom properties for light/dark themes) plus hand-written component classes that reproduce the original Tailwind-based UI (Dash has no Tailwind build step, so this is a plain CSS port). Dash auto-loads everything in `assets/`. |
| `assets/*.png`, `assets/*.webp` | Logos and figures used across the site (header/footer logos, About/Methodology page figures, partner logos). Referenced from Python with `/assets/<file>` (Dash's `get_asset_url` convention). |
| `assets/data/<country>/*.json`, `*.geojson` | Bundled analytics snapshots and municipality boundary files per country - the offline fallback data source (see Section 3). |
| `README.md` | This file. |
| `.example.env` | Template for environment variables; copy to `.env` for local dev. |
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

The app follows the **same fallback strategy** as the original Next.js
app: try Supabase first, fall back to bundled JSON if Supabase isn't
configured or a query fails. This means **the app works out of the box
with zero configuration** - which matters for a first Posit Connect
deployment before a database connection is provisioned.

### 3.1 Primary source: Supabase (`analytics` schema)

When `NEXT_PUBLIC_SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are set
(see `.example.env`), `queries.py` opens a `supabase-py` client and reads
from the same tables the original app used:

| Table | Purpose |
|---|---|
| `analytics.dataset_releases` | One row per country/year release (`is_active` flags the current release). |
| `analytics.municipalities` | The registry of local-government units (id, composite key, province/district, country code). |
| `analytics.score_definitions` | Pillar-level score metadata (Prosperity/Infrastructure/Livability), including which component indicators roll up into each. |
| `analytics.score_components` | The individual component indicators that make up each score. |
| `analytics.indicators` / `analytics.indicator_sources` | Indicator metadata and source/provenance notes shown in the metadata panel. |
| `analytics.municipality_score_values` | The actual 0-100 score values per municipality/release/year. |
| `analytics.municipality_indicator_values` | Raw/processed indicator values per municipality. |
| `analytics.municipality_score_component_values` | Component-level values used for the score-driver waterfall charts. |
| `analytics.municipality_context_values` | Contextual attributes (population, land area, etc.). |
| `analytics.municipality_boundaries` | Boundary/geometry references. |
| `analytics.strategy_inventory_documents` | The strategy/budget document registry for Serbia and Zambia (source status, parsing status, AI-readiness, translation status). |

`queries.get_analytics_dataset()` loads the bundled JSON as the base
dataset (it already contains fully joined/derived scores, since it was
produced by the same upstream pipeline that feeds Supabase) and, if
Supabase is reachable, overlays the *live* score values for the active
release on top of it. Any Supabase error is caught and silently ignored,
leaving the JSON values in place - the app never hard-fails because of a
database outage.

### 3.2 Fallback source: bundled JSON snapshots

`assets/data/<country>/`:

- `analytics-data.json` - a generated snapshot containing, per country:
  the release metadata (`release.key`, `release.year`), the list of
  `years` available, `provinces`, `metrics` (score + indicator
  definitions with labels/units), `scoreDefinitions` (pillar -> component
  mapping), `indicatorDefinitions`, `coverage` counts, and the full
  `municipalities` array (one row per municipality per year, with nested
  `scores`, `indicators`, `scoreComponents`, and `context` objects).
- `municipalities.geojson` - the boundary `FeatureCollection` used to draw
  the choropleth map, keyed by the same `compositeKey` used in
  `analytics-data.json`.
- `strategy_inventory.sample.json` (Serbia and Zambia only) - a sample/
  preview strategy-document inventory in the same shape as the
  `strategy_inventory_documents` Supabase table, used when no database is
  configured. The app labels this data as a **sample/preview dataset** in
  the UI (`is_sample_data: true`) so it is never mistaken for validated
  source data.

These snapshots are the same generated files the original Next.js app
bundled (`src/generated/*.json`, `public/data/*.geojson`) - they were not
recreated from scratch, just relocated into `assets/data/` per this
migration's requirement that all static data ship inside `assets/`.

### 3.3 Where each page's data comes from

| Page | Data source |
|---|---|
| Home | `queries.get_analytics_dataset()` per country, aggregated into global coverage stats. |
| About, Methodology, Roadmap, Resources, Release Notes | 100% static content from `constants.py` - no database calls. |
| Country landing page | `queries.load_country_dataset()` + `queries.build_country_home_model()` (population/area totals, province groupings) + `queries.get_country_landing_actions()` / `get_plan_availability_disclosure()`. |
| Country analytics page | `queries.get_analytics_page_data()` - the single function that assembles filters, the selected municipality, map features, scatter points, score-driver rows, and waterfall groups for the current filter selection. |
| Strategy inventory page | `queries.get_strategy_inventory_dataset()` (Supabase table or sample JSON) + `queries.get_strategy_inventory_summary()` / `get_readiness_category()` for the coverage math and readiness classification. |

### 3.4 What was intentionally simplified

Two things from the original product were deliberately **not** ported
1:1, to keep this migration scoped to the 8 requested files and to
Dash's request/response (not streaming) execution model:

1. **The multi-stage AI Planning Brief pipeline.** The original app ran a
   7-stage LLM workflow (indicator narrative -> local plan context ->
   national plan context -> web search context -> plan alignment -> SWOT
   -> investment recommendations) with per-stage caching in Supabase and
   PDF parsing of source planning documents. This migration wires the
   relevant environment variables (`OPENAI_API_KEY`, `OPENAI_MODEL`,
   `EXA_API_KEY`, `AI_GENERATION_ENABLED`, etc. - see `.example.env`) and
   documents where they belong in `constants.py`, but does not
   reimplement the pipeline itself in `app.py`. Wiring it up is a natural
   next step and would live in `queries.py` (an `ai.py` module, in the
   original) as additional functions called from a new "AI Brief" tab.
2. **Live plan-document availability per municipality.** The original app
   tracked, per municipality/province, whether a local or SNG planning
   document link was on file (used for the "Development plan source
   availability" disclosure on each country page). Because that specific
   join table wasn't part of the `analytics` schema exported above, the
   Dash version renders the same disclosure UI and groups municipalities
   by province, but does not yet mark individual availability - see the
   `build_plan_availability_groups()` docstring in `app.py`.

Everything else - every page, every chart type, every filter, every piece
of static content, the full design system, dark mode, and the CSV export
- is fully implemented and interactive.

---

## 4. Running locally

```bash
# 1. Create and activate a virtual environment (Python 3.9+)
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) configure environment variables
cp .example.env .env
# edit .env if you want to connect a real Supabase project; otherwise
# leave it as-is and the app will use the bundled JSON data.

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
   folder (with its `data/` subfolder). Do not include `.env` - set
   environment variables through Connect's **Vars** pane instead.
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
3. In the content's **Vars** settings on Connect, add any of the
   variables from `.example.env` you want to set (Supabase credentials,
   `AI_*` variables, etc.). None are required for the app to run.
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
