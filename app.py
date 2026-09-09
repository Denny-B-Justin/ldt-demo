"""
app.py
================
Main Dash application: page layouts, routing, and callbacks for the Local
Development Tracker (LDT).

This is a from-scratch Python/Dash re-implementation of the Next.js app
that lived in this repository. Every route in the original App Router
tree has a corresponding page-builder function below:

    Next.js route                         -> builder function
    ---------------------------------------------------------
    /                                      -> render_home()
    /about                                 -> render_about()
    /methodology                           -> render_methodology()
    /roadmap                               -> render_roadmap()
    /resources                             -> render_resources()
    /release-notes                         -> render_release_notes()
    /{country}                             -> render_country_landing(slug)
    /{country}/analytics                   -> render_analytics(slug)
    /{country}/strategy-inventory          -> render_strategy_inventory(slug)

Routing is done client-side with `dcc.Location` + a single router
callback (`render_page_content`) that swaps the contents of the
`#ldt-page-content` div - the same "app shell + swapped body" pattern
Next.js's root layout implements with `{children}`.

Run locally with:  python app.py
Run for production: gunicorn app:server
"""

from __future__ import annotations

import io
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs

import dash
import pandas as pd
from dash import ALL, Input, Output, State, callback_context, dcc, html, no_update
from dash.exceptions import PreventUpdate

import constants
import datastore
import memo
import queries
import utils

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=os.environ.get("LDT_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# App instantiation
# --------------------------------------------------------------------------
#
# The app is deployed behind a reverse proxy at
# Dash needs to know
# that prefix so it emits correct URLs for its own internal assets
# (_dash-layout, _dash-update-component, /assets/*, etc). Everything else
# (in-app navigation) is done with *relative* "?page=..." links, which work
# unchanged under any deployment prefix, so it does not need to be baked
# into every href.
#
# Override via env var if the app is ever mounted somewhere else.

app = dash.Dash(
    __name__,
    title=constants.APP_TITLE,
    update_title=None,
    suppress_callback_exceptions=True,
    meta_tags=[
        {"name": "viewport", "content": "width=device-width, initial-scale=1"},
        {"name": "description", "content": constants.APP_DESCRIPTION},
    ],
)
server = app.server  # exposed for gunicorn / Posit Connect (see README)
logger.info("Initialized Dash app with %s country workspaces.", len(constants.COUNTRIES))

# Route every dataset read through the filesystem-cached, request-safe data
# layer (instead of live Databricks queries on the request path).
datastore.install_providers()

# In Dash debug mode Werkzeug's reloader runs a supervisor process that also
# imports this module; skip the background threads there (the child process,
# which sets WERKZEUG_RUN_MAIN, is the one that serves).
_IS_RELOADER_PARENT = (
    os.environ.get("DASH_DEBUG", "true").lower() == "true"
    and __name__ == "__main__"
    and os.environ.get("WERKZEUG_RUN_MAIN") != "true"
)

# Kick a background data warm if the local artifacts are missing or stale.
# This never blocks request handling; pages serve from the shipped snapshot /
# bundled data until the fresh copy lands. (Also re-checked cheaply on every
# datastore access, so it self-heals per worker process.)
if not _IS_RELOADER_PARENT:
    datastore.ensure_warm_started()


def _prewarm_process() -> None:
    """One-time, per-process costs paid off the request path: Plotly builds
    its (slow) per-trace-type validators lazily on first use, which otherwise
    lands on a user's first chart interaction (~1s). Touch each trace type and
    the home summary here instead."""
    try:
        # Build one real figure of every kind the app renders. This forces
        # Plotly's lazy, ~1s-on-first-use import of its template + validator
        # machinery (`update_layout(template=...)`) to happen here rather than
        # on a user's first chart.
        import plotly.graph_objects as go

        for trace, template in (
            (go.Choroplethmap(geojson={"type": "FeatureCollection", "features": []}, locations=[], z=[]), "plotly_white"),
            (go.Scatter(x=[0], y=[0]), "plotly_white"),
            (go.Scatter(x=[0], y=[0]), "plotly_dark"),
            (go.Scatter3d(x=[0], y=[0], z=[0]), "plotly_white"),
            (go.Bar(x=[0], y=[0]), "plotly_white"),
        ):
            fig = go.Figure(trace)
            fig.update_layout(template=template, margin=dict(l=0, r=0, t=0, b=0))
            fig.to_plotly_json()
        datastore.home_summary()
        logger.info("Process prewarm complete.")
    except Exception:  # noqa: BLE001
        logger.exception("Process prewarm failed (non-fatal).")


if os.environ.get("LDT_DISABLE_PREWARM", "0") != "1" and not _IS_RELOADER_PARENT:
    import threading as _threading

    _threading.Thread(target=_prewarm_process, name="ldt-prewarm", daemon=True).start()


@server.route("/healthz")
def _healthz():
    from flask import jsonify

    return jsonify({"status": "ok", "data": datastore.data_status()})


@server.route("/ldt/admin/refresh", methods=["POST", "GET"])
def _refresh_data():
    """Force-rebuild the cached datasets from Databricks. Call this from a
    Posit Connect scheduled job after each data release. Guarded by
    LDT_REFRESH_TOKEN when that env var is set."""
    from flask import jsonify, request

    if datastore.REFRESH_TOKEN:
        supplied = request.args.get("token") or request.headers.get("X-LDT-Refresh-Token")
        if supplied != datastore.REFRESH_TOKEN:
            return jsonify({"error": "unauthorized"}), 401

    # A full warm can take minutes; run it in the background and return now so
    # the caller (a scheduled job) doesn't hit a proxy timeout. Pass ?wait=1
    # to block and get the manifest back.
    if request.args.get("wait") == "1":
        try:
            return jsonify({"status": "refreshed", "manifest": datastore.warm(force=True)})
        except Exception as exc:  # noqa: BLE001
            logger.exception("Manual data refresh failed.")
            return jsonify({"status": "error", "detail": str(exc)}), 500

    import threading as _threading

    _threading.Thread(target=datastore._safe_warm, name="ldt-manual-refresh", daemon=True).start()
    return jsonify({"status": "refresh-started", "data": datastore.data_status()}), 202

# --------------------------------------------------------------------------
# App shell (root layout) - equivalent of src/app/layout.tsx
# --------------------------------------------------------------------------
FAVICON_URL = app.get_asset_url("favicon.ico")

app.index_string = """
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        <link rel="icon" type="image/x-icon" href=\"""" + FAVICON_URL + """\">
        {%css%}
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
"""

app.layout = html.Div(
    id="ldt-app-root",
    children=[
        dcc.Location(id="url", refresh=False),
        dcc.Store(id="theme-store", storage_type="local", data={"theme": "light"}),
        # Hidden bridge element: the clientside callback below writes to this
        # element's `title` prop purely as a trigger side-effect so it can
        # apply `data-theme` to <html> whenever theme-store changes, without
        # creating a second writer of theme-store itself (Dash does not
        # allow two callbacks to target the same Output identifier/property
        # unless carefully coordinated with allow_duplicate, which adds
        # unnecessary complexity here).
        html.Div(id="theme-applier", style={"display": "none"}),
        html.Div(id="ldt-header-slot"),
        html.Div(id="ldt-page-content"),
        html.Div(id="ldt-footer-slot"),
        # Hidden download helper for the country SNG metrics CSV export
        dcc.Download(id="sng-csv-download"),
    ],
)


# ==========================================================================
# STATIC CONTENT PAGES
# ==========================================================================

def render_home() -> html.Main:
    """Port of src/app/page.tsx"""
    logger.debug("Rendering homepage from the cached home summary.")
    # The home page is static chrome plus three headline numbers. Those come
    # from a tiny pre-computed summary (datastore), never a live Databricks
    # read, so this page renders instantly regardless of warehouse state.
    summary = datastore.home_summary()
    total_lsgs = summary.get("lsgsLoaded")
    latest_year = summary.get("latestYear")

    home_stats = [
        {"value": str(summary.get("countryWorkspaces") or len(constants.COUNTRIES)), "label": "Country workspaces"},
        {"value": f"{total_lsgs:,}" if total_lsgs else "—", "label": "LSGs currently loaded"},
        {"value": str(latest_year) if latest_year else "—", "label": "Latest data year"},
    ]

    return html.Main(
        children=[
            html.Section(
                className="hero-section",
                children=html.Div(
                    className="hero-inner",
                    children=[
                        html.H1("Local Development Tracker for public investment decisions."),
                        html.P(
                            "A country workspace for comparing local development conditions, "
                            "reading municipality-level score drivers, and linking planning "
                            "evidence to public investment choices.",
                            className="lede",
                        ),
                        html.Div(className="stat-grid", children=[utils.stat_card(s["value"], s["label"]) for s in home_stats]),
                        html.Div(
                            id="country-workspaces",
                            className="filters-card",
                            style={"maxWidth": "48rem"},
                            children=[
                                html.Label("", htmlFor="home-country-select", className="visually-hidden"),
                                html.Div(
                                    className="filters-grid",
                                    style={"gridTemplateColumns": "1fr auto"},
                                    children=[
                                        dcc.Dropdown(
                                            id="home-country-select",
                                            options=[{"label": "Select country workspace", "value": ""}]
                                            + [{"label": c["name"], "value": c["slug"]} for c in constants.COUNTRIES],
                                            value="",
                                            clearable=False,
                                        ),
                                        html.Button("Open data \u2192", id="home-country-open", n_clicks=0, className="btn"),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
            ),
            html.Section(
                className="page-container-wide",
                style={"marginTop": "3rem"},
                children=html.Article(
                    className="section-card",
                    children=[
                        html.P("Public investment lens", className="eyebrow"),
                        html.H2("From local evidence to investment decisions"),
                        html.P(
                            "The PIL framework links local development conditions, planning "
                            "evidence, and investment prioritization so users can move from "
                            "diagnostics to practical public investment conversations.",
                            className="lede",
                        ),
                        html.Div(
                            style={"marginTop": "1.5rem", "borderRadius": "1.25rem", "border": "1px solid var(--border-soft)", "background": "#fff", "padding": "1rem"},
                            children=html.Img(src=app.get_asset_url("PIL_Diagram_v2.png"), style={"width": "100%", "height": "auto", "borderRadius": "1rem"}),
                        ),
                    ],
                ),
            ),
            html.Section(
                className="page-container-wide",
                style={"margin": "3rem auto"},
                children=html.Article(
                    className="section-card",
                    children=[
                        html.P("What the LDT provides", className="eyebrow"),
                        html.Div(className="grid-4", style={"marginTop": "1.25rem"}, children=[
                            utils.capability_card(c["title"], c["body"]) for c in constants.HOME_CAPABILITY_CARDS
                        ]),
                    ],
                ),
            ),
        ]
    )


def render_about() -> html.Main:
    """Port of src/app/about/page.tsx"""
    country_rows = [
        html.Tr([
            html.Td(row["country"], style={"fontWeight": 600, "color": "var(--foreground)"}),
            html.Td(row["focus"]), html.Td(row["level_one"]), html.Td(row["level_two"]),
            html.Td(row["strategies"]), html.Td(row["topic"]),
        ]) for row in constants.ABOUT_COUNTRY_ROWS
    ]

    return html.Main(
        className="page-container",
        children=[
            html.Section(className="page-hero-card", children=[
                html.P("pim-pam.net Geospatial Planning and Budgeting Tools", className="eyebrow"),
                html.H1("Local Development Tracker QuickStart"),
                html.P("This version: May 23, 2026", className="page-meta"),
                html.P(
                    "This note sets out the motivation, method, and early country applications "
                    "for the pim-pam.net Geospatial Planning and Budgeting Local Development "
                    "Tracker tool. The LDT is designed to identify key development and public "
                    "investment gaps at sub-national levels, illustrated through applications "
                    "in Nepal, Serbia, and Zambia.",
                    className="lede",
                ),
            ]),
            utils.section_card("The sub-national challenge", [
                html.P(
                    "Sub-national governments are vital to realizing frontline development "
                    "outcomes, including territorial development and job creation. Yet "
                    "relevant SNG levels, population size, and geographic scale vary "
                    "substantially across countries."
                ),
                html.P(
                    "Statistical and administrative data concerning key development "
                    "indicators may be missing or outdated. SNGs may also lack local "
                    "development strategies that best address their challenges and "
                    "opportunities. Big data from non-traditional and geospatial sources, "
                    "including satellites, can help address these gaps."
                ),
                html.P(
                    "The GPB LDT enables rapid analysis of sub-national development "
                    "indicators across Prosperity, Livability, and Infrastructure. It "
                    "deploys a curated list of development indicators, then uses data "
                    "analytics, visualization, and AI extensions to help users identify "
                    "patterns, trends, and planning insights."
                ),
                html.P(
                    "At the individual SNG level, local development strategies are often "
                    "the starting point for understanding priorities. These documents are "
                    "often dispersed, voluminous, uneven in quality, or out of date. The "
                    "GPB LDT applies systematic AI analytics to assemble as comprehensive a "
                    "repository of local strategy documents as possible."
                ),
            ]),
            utils.section_card("The method: two layers, any country", [
                html.P(
                    "The GPB LDT workflow has two complementary layers. The first builds a "
                    "sub-national data baseline. The second maps development strategies and "
                    "translates the evidence into planning and public investment options.",
                    className="lede",
                ),
            ]),
            utils.section_card("Build the sub-national evidence base", eyebrow="Layer 1", children=[
                utils.figure_card("about-ldt-size-distribution.png", "Municipality population distribution chart", "Figure. Understand the size distribution of localities."),
                html.Div(className="grid-2", style={"marginTop": "1.25rem"}, children=[
                    html.Div(className="content-card", children=[html.H3(s["title"]), html.P(s["body"])]) for s in constants.ABOUT_LAYER_ONE_STEPS
                ]),
            ]),
            utils.section_card("Map strategies and translate diagnostics into PIM options", eyebrow="Layer 2", children=[
                html.P(
                    "The second layer connects the data baseline and multi-level government "
                    "development strategies to the planning process.",
                    className="lede",
                ),
                html.Ol(className="grid-2", style={"marginTop": "1.25rem", "paddingLeft": 0, "listStyle": "none"}, children=[
                    html.Li(className="content-card", children=[
                        html.Span(f"Step {i + 1}", className="badge badge-solid", style={"marginBottom": "0.5rem", "display": "inline-flex"}),
                        html.P(step),
                    ]) for i, step in enumerate(constants.ABOUT_LAYER_TWO_STEPS)
                ]),
            ]),
            utils.section_card("Figure 1. Panel of GPB LDT country demo highlights", [
                html.Div(className="grid-2", style={"marginTop": "1.25rem"}, children=[
                    utils.figure_card(f["src"], f["alt"], f["caption"]) for f in constants.ABOUT_HIGHLIGHT_FIGURES
                ]),
            ]),
            utils.section_card("Replicability: adding the next country", [
                html.P(
                    "The LDT has been designed for replication across country settings. The "
                    "workflow does not depend on one country's administrative system, data "
                    "architecture, or planning terminology. Country, sub-national level, "
                    "boundary file, indicator set, population layer, strategy documents, and "
                    "complementary administrative data are inputs to a common method."
                ),
                html.P(
                    "Global geospatial and big-data sources can provide a consistent "
                    "first-pass baseline for nearly any country and sub-national geography. "
                    "Country-specific data can then be added where available to improve "
                    "relevance and interpretation."
                ),
                html.P(
                    "The main time driver is not redesigning the method. It is the "
                    "availability, quality, and validation of country boundaries, local "
                    "strategies, and complementary administrative data. Once these inputs are "
                    "assembled, the LDT provides a repeatable structure for turning local "
                    "evidence into planning insights."
                ),
            ]),
            utils.section_card("Key limitations and validation needs", [
                html.P(
                    "The LDT is most useful when its limitations are explicit. It provides a "
                    "structured starting point for local development diagnostics, not a final "
                    "judgment on local performance or project priority.",
                    className="lede",
                ),
                html.Div(className="grid-2", style={"marginTop": "1.25rem"}, children=[
                    html.Div(className="limitation-card", children=[html.H3(item["title"]), html.P(item["body"])]) for item in constants.ABOUT_LIMITATIONS
                ]),
                html.P(
                    "The central principle is simple: use the LDT to make local development "
                    "patterns visible, then validate, contextualize, and translate those "
                    "patterns through the country's planning and PIM systems.",
                    className="content-card", style={"marginTop": "1.25rem"},
                ),
            ]),
            utils.section_card("Selected country findings", [
                html.P(
                    "The three country applications below illustrate how the same method "
                    "adapts to different planning contexts: filling local evidence gaps "
                    "where strategies are missing, moving from diagnostics to "
                    "investment-ready project matching, and focusing on a specific class of "
                    "localities such as mining districts.",
                    className="lede",
                ),
                html.Div(className="ldt-table-wrap", style={"marginTop": "1.25rem"}, children=html.Table(className="ldt-table", children=[
                    html.Thead(html.Tr([html.Th(h) for h in ["Country", "Level of focus", "# SNGs (Level 1)", "# SNGs (Level 2)", "% with strategies", "Focus topic"]])),
                    html.Tbody(country_rows),
                ])),
                html.Div(className="footnotes", style={"marginTop": "0.75rem"}, children=[
                    html.P("* Provincial strategies are available."),
                    html.P("** For Serbia, 174 if Kosovo is included."),
                    html.P("*** For Serbia, the 94% figure does not include Kosovo."),
                ]),
            ]),
            html.Section(className="grid-3", children=[
                html.Article(className="country-finding-card", children=[html.H2(item["title"]), *[html.P(p) for p in item["paragraphs"]]])
                for item in constants.ABOUT_COUNTRY_FINDINGS
            ]),
            html.Section(className="grid-2", children=[
                utils.figure_card(f["src"], f["alt"], f["caption"]) for f in constants.ABOUT_FIGURE_PAIR
            ]),
            utils.section_card("Further resources and contacts", [
                html.P(
                    "Country teams interested in applying these approaches may schedule a "
                    "3-4 hour GPB LDT Masterclass, apply the tools in their country context, "
                    "or request a tailored briefing on related Infrastructure Governance 2.0 "
                    "diagnostics and other pim-pam.net digital tools."
                ),
                html.P(
                    "Contact the World Bank Global PIM-PAM Solutions Team: Kai-Alexander "
                    "Kaiser, Hyunseok Kim, Fabienne Mroczka, and Kaushiki Singh."
                ),
                html.P(
                    "The team thanks the global partners of the World Bank Financial "
                    "Management Umbrella Program and the Japan Quality of Infrastructure "
                    "Investment Partnership program for supporting this work."
                ),
            ]),
            utils.section_card("Selected references", [
                html.Ul(style={"paddingLeft": "1.25rem"}, children=[html.Li(ref) for ref in constants.ABOUT_REFERENCES]),
            ]),
        ],
    )


def render_methodology() -> html.Main:
    """Port of src/app/methodology/page.tsx"""
    return html.Main(
        className="page-container",
        children=[
            html.Section(className="page-hero-card", children=[
                html.P("Methodology", className="eyebrow"),
                html.H1("Indicator logic, data processing, and score calculation"),
                html.P(
                    "The Local Development Tracker turns geospatial, environmental, "
                    "infrastructure, and planning data into comparable local-government "
                    "indicators. This page explains how indicators are selected, processed, "
                    "normalized, and aggregated into the Prosperity, Infrastructure, and "
                    "Livability scores used throughout the app.",
                    className="lede",
                ),
            ]),
            utils.section_card("Overview", [
                html.P(
                    "The methodology is designed for country replication. Each country "
                    "keeps its own administrative labels and planning context, while the "
                    "analytical logic stays consistent: collect local indicators, harmonize "
                    "them to the relevant subnational units, convert them into comparable "
                    "scores, and expose the results for maps, scatterplots, driver "
                    "analysis, and planning review."
                ),
                html.P(
                    "The framework is intentionally transparent. Users should be able to "
                    "see the indicator source, understand how raw data becomes a score, and "
                    "interpret the result as screening evidence for further validation."
                ),
            ]),
            utils.section_card("PIL framework diagram", eyebrow="Analytical architecture", children=[
                html.P(
                    "The PIL framework organizes local development evidence around "
                    "Prosperity, Infrastructure, and Livability. The diagram shows how "
                    "indicator evidence can be connected to planning interpretation and "
                    "investment prioritization.",
                    className="lede",
                ),
                html.Div(
                    style={"marginTop": "1.5rem", "borderRadius": "1.25rem", "border": "1px solid var(--border-soft)", "background": "#fff", "padding": "1rem"},
                    children=html.Img(src=app.get_asset_url("PIL_Diagram_v2.png"), style={"width": "100%", "height": "auto", "borderRadius": "1rem"}),
                ),
            ]),
            utils.section_card("Indicator Selection Logic", [
                html.P(
                    "Indicators are selected to balance policy relevance with practical "
                    "data coverage. The aim is not to include every possible local "
                    "development measure, but to build a coherent evidence base that can "
                    "be maintained and compared across local units."
                ),
                html.Ul(style={"paddingLeft": "1.25rem"}, children=[html.Li(i) for i in constants.METHODOLOGY_INDICATOR_SELECTION]),
            ]),
            html.Section(className="grid-3", children=[
                html.Article(className="content-card", children=[
                    html.H2(p["title"]), html.P(p["body"]),
                    html.Ul(style={"paddingLeft": "1.25rem"}, children=[html.Li(i) for i in p["items"]]),
                ]) for p in constants.METHODOLOGY_PILLARS
            ]),
            utils.section_card("Data Acquisition", [
                html.P(
                    "The LDT combines scalable global datasets with country-specific "
                    "sources where available. Each source is selected for its relevance to "
                    "local development, spatial coverage, and ability to be processed into "
                    "local-government units.",
                    className="lede",
                ),
                html.Div(className="grid-3", style={"marginTop": "1.25rem"}, children=[
                    html.Article(className="content-card", children=[
                        html.H3(group["title"]),
                        html.Ul(style={"paddingLeft": "1.25rem"}, children=[html.Li(i) for i in group["items"]]),
                    ]) for group in constants.METHODOLOGY_DATA_SOURCES
                ]),
            ]),
            utils.section_card("Preprocessing and Integration", [
                html.P(
                    "Raw data are prepared before they are exposed in the app. The "
                    "preprocessing pipeline converts heterogeneous input formats into "
                    "consistent local-unit records that can be compared, mapped, and "
                    "summarized.",
                    className="lede",
                ),
                html.Div(className="grid-2", style={"marginTop": "1.25rem"}, children=[
                    html.Article(className="content-card", children=[html.H3(s["title"]), html.P(s["body"])]) for s in constants.METHODOLOGY_PREPROCESSING_STEPS
                ]),
            ]),
            utils.section_card("Score Calculation and Aggregation", [
                html.P(
                    "Score calculation follows a simple interpretation rule: local units "
                    "are compared against other local units in the same release, and "
                    "higher scores indicate stronger relative performance for the selected "
                    "indicator or pillar unless the metadata says otherwise."
                ),
                html.Ul(style={"paddingLeft": "1.25rem"}, children=[html.Li(i) for i in constants.METHODOLOGY_SCORING_STEPS]),
            ]),
            utils.section_card("Limitations and Interpretation", [
                html.Div(className="grid-3", style={"marginTop": "1.25rem"}, children=[
                    html.Article(className="content-card", children=[
                        html.H3(lim["title"]),
                        html.Ul(style={"paddingLeft": "1.25rem"}, children=[html.Li(i) for i in lim["items"]]),
                    ]) for lim in constants.METHODOLOGY_LIMITATIONS
                ]),
            ]),
            utils.section_card("References and Further Information", [
                html.P(
                    "Indicator descriptions, source references, and interpretation notes "
                    "are surfaced through the indicator metadata views in the analytics "
                    "workspace. Users should read charts and scores as decision-support "
                    "evidence for discussion, validation, and prioritization rather than as "
                    "final project-selection decisions."
                ),
            ]),
        ],
    )


def render_resources() -> html.Main:
    """Port of src/app/resources/page.tsx"""
    def resource_card(resource):
        return html.A(
            href=resource["href"], target="_blank", className="resource-card",
            children=[
                html.Span(resource["format"], className="badge badge-solid"),
                html.H3(resource["title"], style={"marginTop": "0.75rem"}),
                html.P(resource["description"]),
                html.Span("Open resource \u2197", style={"color": "var(--accent)", "fontWeight": 600}),
            ],
        )

    def country_pack_card(pack):
        file_items = [
            html.Li(html.A(href=f["href"], target="_blank", children=[
                html.Span(f["title"], style={"display": "block", "fontWeight": 600}),
                html.Span(f["format"], className="badge badge-outline", style={"marginTop": "0.25rem"}),
            ])) for f in pack["files"]
        ] if pack["files"] else [html.P(pack["empty_state"], className="small")]

        return html.Article(className="content-card", children=[
            html.P(pack["country"], className="eyebrow"),
            html.H3(pack["title"]),
            html.P(pack["description"]),
            html.A("\U0001F4C1 Open country folder", href=pack["href"], target="_blank", style={"color": "var(--accent)", "fontWeight": 600}),
            html.Div(style={"marginTop": "1rem", "borderTop": "1px solid var(--border-soft)", "paddingTop": "0.75rem"}, children=[
                html.P("Included materials", className="eyebrow"),
                html.Ul(file_items, style={"paddingLeft": "1.1rem"}),
            ]),
        ])

    return html.Main(
        className="page-container",
        children=[
            html.Section(children=[
                html.P("Resources", className="eyebrow"),
                html.H1("LDT documents and working materials"),
                html.P(
                    "A curated set of reference materials for understanding the Local "
                    "Development Tracker, sharing the GPB approach, and supporting "
                    "country-facing discussions.",
                    className="lede",
                ),
            ]),
            html.Section(children=[
                html.P("Core LDT materials", className="eyebrow"),
                html.H2("Start here"),
                html.Div(className="grid-3", style={"marginTop": "1.25rem"}, children=[resource_card(r) for r in constants.LDT_RESOURCE_FILES]),
            ]),
            html.Section(children=[
                html.P("Country resource spaces", className="eyebrow"),
                html.H2("Documents, demos, and analyses by country"),
                html.Div(className="grid-3", style={"marginTop": "1.25rem"}, children=[country_pack_card(p) for p in constants.COUNTRY_RESOURCE_PACKS]),
            ]),
        ],
    )


def render_roadmap() -> html.Main:
    """Port of src/app/roadmap/page.tsx"""
    def phase_card(phase):
        return html.Article(
            className="roadmap-phase",
            style={"borderLeftColor": phase["accent"]},
            children=[
                html.Span(f"{phase['version']} \u2022 {phase['sprint']} \u2022 {phase['window']}", className="roadmap-version", style={"color": phase["accent"]}),
                html.H3(phase["name"]),
                html.P(phase["horizon"], className="small muted"),
                html.P(phase["goal"]),
                html.Ul([html.Li(e) for e in phase["epics"]]),
                html.P([html.Strong("Release gate: "), phase["gate"]], className="small"),
            ],
        )

    def workstream_card(ws):
        return html.Article(className="content-card", children=[
            html.H3(ws["name"]), html.P(ws["description"]),
            html.Ul(style={"paddingLeft": "1.1rem"}, children=[html.Li(s) for s in ws["steps"]]),
        ])

    def guardrail_card(g):
        return html.Article(className="content-card", children=[html.H3(g["title"]), html.P(g["body"])])

    return html.Main(
        className="page-container",
        children=[
            html.Section(className="page-hero-card", children=[
                html.P("Roadmap", className="eyebrow"),
                html.H1("From analytics to an evidence-to-investment platform"),
                html.Div(className="grid-3", style={"marginTop": "1.5rem"}, children=[utils.stat_card(m["value"], m["label"]) for m in constants.ROADMAP_NORTH_STAR_METRICS]),
            ]),
            utils.section_card("Release sequence: v1.5 \u2192 v2 (MEGA migration)", [
                html.Div(className="roadmap-timeline", children=[phase_card(p) for p in constants.ROADMAP_PHASES]),
            ]),
            utils.section_card("Delivery workstreams", [
                html.Div(className="grid-2", style={"marginTop": "1rem"}, children=[workstream_card(w) for w in constants.ROADMAP_WORKSTREAMS]),
            ]),
            utils.section_card("Release gates", [
                html.Ul(style={"paddingLeft": "1.25rem"}, children=[html.Li(g) for g in constants.ROADMAP_RELEASE_GATES]),
            ]),
            utils.section_card("AI and product guardrails", [
                html.Div(className="grid-2", style={"marginTop": "1rem"}, children=[guardrail_card(g) for g in constants.ROADMAP_GUARDRAILS]),
            ]),
            utils.section_card("Execution backlog for this roadmap page", [
                html.Ul(style={"paddingLeft": "1.25rem"}, children=[html.Li(b) for b in constants.ROADMAP_EXECUTION_BACKLOG]),
            ]),
        ],
    )


def render_release_notes() -> html.Main:
    """Port of src/app/release-notes/page.tsx"""
    def release_card(release):
        sections = []
        for section in release["sections"]:
            sections.append(html.Div(className="release-section", children=[
                html.H4(section["title"]),
                html.Ul([html.Li(item) for item in section["items"]]),
            ]))
        return html.Article(className="release-card", children=[
            html.Div(className="release-header", children=[
                html.H2(release["version"], style={"margin": 0}),
                html.Span(release["type"], className="badge badge-solid"),
                html.Span(release["date"], className="small muted"),
            ]),
            html.P(release["summary"], style={"marginTop": "0.75rem"}),
            html.Div(sections, style={"marginTop": "1rem"}),
        ])

    return html.Main(
        className="page-container",
        children=[
            html.Section(children=[
                html.P("Release Notes", className="eyebrow"),
                html.H1("Version history"),
                html.P(
                    "A versioned changelog of Local Development Tracker releases, from the "
                    "first public analytics application through the current multi-country "
                    "workspace.",
                    className="lede",
                ),
            ]),
            html.Section(className="grid-4", style={"gridTemplateColumns": "repeat(4, 1fr)"}, children=[
                html.Div(className="content-card", children=[html.H3(t["label"]), html.P(t["description"], className="small")]) for t in constants.RELEASE_VERSION_TYPES
            ]),
            html.Section(style={"display": "flex", "flexDirection": "column", "gap": "1.25rem"}, children=[release_card(r) for r in constants.RELEASES]),
        ],
    )


# ==========================================================================
# COUNTRY LANDING PAGE - port of src/components/country/country-landing-page.tsx
# ==========================================================================

def render_country_landing(slug: str) -> html.Main:
    country = constants.COUNTRY_BY_SLUG.get(slug)
    if not country:
        return render_not_found()

    dataset = queries.load_country_dataset(country["code"])
    model = queries.build_country_home_model(country, dataset)
    admin = country["admin_labels"]
    lower_s, lower_p = admin["lower"]["singular"], admin["lower"]["plural"]
    higher_s, higher_p = admin["higher"]["singular"], admin["higher"]["plural"]
    lower_s_label, lower_p_label, higher_p_label = utils.lower_first(lower_s), utils.lower_first(lower_p), utils.lower_first(higher_p)

    actions = queries.get_country_landing_actions(country)
    left_actions = [a for a in actions if a["align"] == "left"]
    right_actions = [a for a in actions if a["align"] == "right"]

    guide = country["admin_level_guide"]
    admin_count_summary = (
        f"In the {model['latestYear']} LDT release, Admin level 1 includes "
        f"{model['higherCount']} {higher_p_label}, and Admin level 2 includes "
        f"{model['lowerCount']} {lower_p_label}."
    )

    plan_disclosure = queries.get_plan_availability_disclosure(country)

    return html.Main(
        children=[
            html.Section(className="hero-section", children=html.Div(className="hero-inner", children=[
                html.H1(f"{country['name']} subnational analytics for local economic development"),
                html.P(
                    f"Review {higher_p_label} and {lower_p_label} coverage, compare population "
                    f"and PIL indicators, and trace which planning documents are available for "
                    f"analysis.",
                    className="lede",
                ),
                html.Div(className="hero-actions", children=[
                    html.Div(style={"display": "flex", "gap": "1rem", "flexWrap": "wrap"}, children=[
                        utils.link_button(a["label"], a["href"], a["variant"]) for a in left_actions
                    ]),
                    html.Div(style={"display": "flex", "gap": "1rem", "flexWrap": "wrap", "marginLeft": "auto"}, children=[
                        utils.link_button(a["label"], a["href"], a["variant"]) for a in right_actions
                    ]),
                ]),
            ])),
            html.Section(className="page-container-wide", style={"marginTop": "3.5rem"}, children=html.Article(className="section-card", children=[
                html.P("Country snapshot", className="eyebrow"),
                html.Div(className="snapshot-grid", children=[
                    html.Div(className="snapshot-tile", children=[html.P("Population covered", className="eyebrow"), html.P(model["populationLabel"], className="snapshot-value")]),
                    html.Div(className="snapshot-tile", children=[html.P("Land area covered", className="eyebrow"), html.P(model["areaLabel"], className="snapshot-value")]),
                    html.Div(className="snapshot-tile", children=[
                        html.P("National development plan", className="eyebrow"),
                        html.A(country["profile"]["strategy"]["title"], href=country["profile"]["strategy"]["url"], target="_blank",
                               className="snapshot-value", style={"display": "block", "textDecoration": "underline"}),
                    ]),
                ]),
            ])),
            html.Section(className="page-container-wide", style={"marginTop": "2.5rem"}, children=html.Article(className="section-card", children=[
                html.P("Country context", className="eyebrow"),
                html.H2("Why this workspace matters"),
                html.P(country["profile"]["context"]["summary"], className="lede"),
                html.Div(className="source-links", children=[
                    html.A(s["label"], href=s["href"], target="_blank", className="source-link-pill") for s in country["profile"]["context"]["source_links"]
                ]),
                html.Div(className="grid-3", style={"marginTop": "1.25rem"}, children=[
                    html.Div(h, className="content-card") for h in country["profile"]["context"]["highlights"]
                ]),
            ])),
            html.Section(className="page-container-wide", style={"marginTop": "2.5rem"}, children=html.Article(className="section-card", children=[
                html.P("Administrative context", className="eyebrow"),
                html.H2(f"Admin levels 1 and 2 in {country['name']}"),
                html.P(guide["summary"], className="lede"),
                html.P(admin_count_summary),
                html.P(guide["note"]),
                html.Div(className="admin-level-grid", children=[
                    html.Div(className="admin-level-tile", children=[
                        html.P(level["label"], className="eyebrow"),
                        html.P(level["name"], style={"fontSize": "1.2rem", "fontWeight": 700, "margin": "0.25rem 0"}),
                        html.P(level["description"]),
                    ]) for level in guide["levels"]
                ]),
                html.Div(className="source-links", children=[
                    html.A(s["label"], href=s["href"], target="_blank", className="source-link-pill") for s in guide["source_links"]
                ]),
            ])),
            html.Section(className="page-container-wide", style={"margin": "2.5rem auto 4rem"}, children=html.Article(className="section-card", children=[
                html.P("Administrative levels", className="eyebrow"),
                html.H2(f"{higher_p} and {lower_p}"),
                html.P(
                    f"This country entry point focuses on the subnational tiers used in "
                    f"the LDT: {model['higherCount']} {higher_p_label} and "
                    f"{model['lowerCount']} {lower_p_label} in the {model['latestYear']} release.",
                ),
                html.Details(open=False, style={"marginTop": "1.25rem"}, children=[
                    html.Summary(plan_disclosure["description"], style={"cursor": "pointer", "color": "var(--muted-foreground)"}),
                    html.Div(style={"marginTop": "1rem"}, children=build_plan_availability_groups(country, dataset)),
                ]),
                html.Div(style={"marginTop": "1.5rem"}, children=build_sng_table(country, dataset)),
                html.Button(f"Download {lower_s_label} metrics CSV", id={"type": "sng-csv-button", "country": country["slug"]}, n_clicks=0, className="btn btn-secondary", style={"marginTop": "1rem"}),
            ])),
        ]
    )


def build_plan_availability_groups(country: Dict[str, Any], dataset: Dict[str, Any]) -> List[html.Div]:
    """Port of the plan-source availability disclosure in country-detail-loader.tsx."""
    latest_year = max(dataset.get("years", [dataset.get("release", {}).get("year", 0)]))
    rows = [m for m in dataset["municipalities"] if m["year"] == latest_year]
    plan_level = country["planning_documents"]["plan_source_admin_level"]

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for m in rows:
        grouped.setdefault(m["province"], []).append(m)

    items = []
    for group_name in sorted(grouped.keys()):
        # Without a live plan-document registry, availability is unknown for
        # every unit in the local JSON fallback; render as "Not tracked" so
        # the UI stays honest about what data is actually loaded.
        unit_names = sorted({m["municipality"] for m in grouped[group_name]}) if plan_level == "lower" else [group_name]
        items.append(html.Div(style={"marginBottom": "0.75rem"}, children=[
            html.P(group_name, style={"fontWeight": 600, "margin": "0 0 0.35rem"}),
            html.Div(style={"display": "flex", "flexWrap": "wrap", "gap": "0.35rem"}, children=[
                html.Span(name, className="badge badge-outline") for name in unit_names[:12]
            ] + ([html.Span(f"+{len(unit_names) - 12} more", className="badge badge-outline")] if len(unit_names) > 12 else [])),
        ]))
    return items


def build_sng_table(country: Dict[str, Any], dataset: Dict[str, Any], preview: int = 8):
    """Port of the SNG metrics table in src/components/nepal/sng-display-section.tsx."""
    latest_year = max(dataset.get("years", [dataset.get("release", {}).get("year", 0)]))
    rows = [m for m in dataset["municipalities"] if m["year"] == latest_year]
    admin = country["admin_labels"]

    header = [admin["lower"]["singular"], admin["higher"]["singular"], "Population", f"Area (km\u00b2)", "Infrastructure", "Livability", "Prosperity"]
    body_rows = []
    for m in rows[:preview]:
        body_rows.append(html.Tr([
            html.Td(m["municipality"]), html.Td(m["province"]),
            html.Td(f"{m['context'].get('population'):,.0f}" if m["context"].get("population") is not None else "n/a"),
            html.Td(utils.fmt(m["context"].get("totalLandAreaKm2"), 1)),
            html.Td(utils.fmt(m["scores"].get("infrastructure_score"))),
            html.Td(utils.fmt(m["scores"].get("livability_score"))),
            html.Td(utils.fmt(m["scores"].get("prosperity_score"))),
        ]))

    return html.Div(children=[
        html.Div(className="ldt-table-wrap", children=html.Table(className="ldt-table", children=[
            html.Thead(html.Tr([html.Th(h) for h in header])),
            html.Tbody(body_rows),
        ])),
        html.P(f"Showing {min(preview, len(rows))} of {len(rows)} {utils.lower_first(admin['lower']['plural'])}. "
               f"Use the {admin['lower']['singular']} analytics page for the full sortable, filterable dataset.",
               className="small muted", style={"marginTop": "0.5rem"}),
    ])


def render_not_found() -> html.Main:
    return html.Main(className="page-container", children=[
        html.H1("Page not found"),
        html.P("The page you're looking for doesn't exist. Return to the ", style={"display": "inline"}),
        html.A("homepage", href="?page=home"),
        html.Span("."),
    ])


def render_error(detail: str = "") -> html.Main:
    """Shown when a Databricks read fails, instead of a bare 500."""
    return html.Main(className="page-container", children=[
        html.H1("Data temporarily unavailable"),
        html.P(
            "The Local Development Tracker could not load data from Databricks "
            "Unity Catalog. This usually clears on its own - try again shortly."
        ),
        html.P(detail, className="small muted") if detail else None,
        html.A("← Back to homepage", href="?page=home", className="ldt-action-button secondary"),
    ])


def render_under_construction(country_name: str) -> html.Main:
    return html.Main(className="page-container", children=[
        html.H1(f"{country_name} workspace"),
        html.P("This country workspace is not yet live. Check back soon, or return to the homepage."),
        html.A("\u2190 Back to homepage", href="?page=home", className="ldt-action-button secondary"),
    ])


# ==========================================================================
# ANALYTICS PAGE - port of src/app/[country]/analytics/page.tsx and
# src/components/analytics/*
# ==========================================================================

ANALYTICS_TABS = [
    {"value": "map", "label": "Map"},
    {"value": "scatter2d", "label": "2D Scatterplot"},
    {"value": "scatter3d", "label": "3D Scatterplot"},
    {"value": "drivers", "label": "Score Drivers"},
]


def render_analytics(slug: str) -> html.Main:
    country = constants.COUNTRY_BY_SLUG.get(slug)
    if not country:
        return render_not_found()

    # First paint: filter bar + selection metadata only. The charts (and their
    # heavy per-tab data) load afterwards through the tab callback, wrapped in
    # dcc.Loading -- so the user only ever waits when they pick something to
    # visualise, not when the page opens.
    page_data = queries.get_analytics_page_data(country["code"], sections=set())
    admin = country["admin_labels"]

    return html.Main(
        className="page-container",
        children=[
            dcc.Store(id="analytics-country-store", data=country["code"]),
            html.Section(children=[
                html.P(f"{country['name']} analytics", className="eyebrow"),
                html.H1(f"{admin['lower']['singular']}-level PIL analytics"),
                html.P(
                    f"Release {page_data['release'].get('key', '')} \u2022 "
                    f"{page_data['coverage'].get('analyticsMunicipalityCount', 0)} "
                    f"{utils.lower_first(admin['lower']['plural'])} loaded.",
                    className="lede",
                ),
            ]),
            html.Div(className="filters-card", children=[
                html.Div(className="filters-grid", children=[
                    html.Div(className="filter-field", children=[
                        html.Label("Year"),
                        dcc.Dropdown(id="analytics-year", options=[{"label": str(y), "value": y} for y in page_data["filters"]["years"]], value=page_data["selected"]["year"], clearable=False),
                    ]),
                    html.Div(className="filter-field", children=[
                        html.Label(admin["higher"]["singular"]),
                        dcc.Dropdown(
                            id="analytics-province",
                            options=[{"label": ("All " + utils.lower_first(admin["higher"]["plural"])) if p == "all" else p, "value": p} for p in page_data["filters"]["provinces"]],
                            value=page_data["selected"]["province"], clearable=False,
                        ),
                    ]),
                    html.Div(className="filter-field", children=[
                        html.Label(admin["lower"]["singular"]),
                        dcc.Dropdown(id="analytics-municipality",
                            options=[{"label": m["label"], "value": m["id"]} for m in page_data["filters"]["municipalities"]],
                            value=page_data["selected"]["municipalityId"],
                            clearable=False,
                            optionHeight=50,),
                    ]),
                    html.Div(className="filter-field", children=[
                        html.Label("Map / X-axis metric"),
                        dcc.Dropdown(id="analytics-metric", options=[{"label": m["label"], "value": m["id"]} for m in page_data["filters"]["metrics"]], value=page_data["selected"]["metricId"], clearable=False),
                    ]),
                ]),
            ]),
            dcc.Tabs(id="analytics-tabs", value="map", className="ldt-tabs", children=[
                dcc.Tab(label=t["label"], value=t["value"], className="tab", selected_className="tab--selected") for t in ANALYTICS_TABS
            ]),
            dcc.Loading(
                html.Div(id="analytics-tab-content", style={"marginTop": "1.5rem"}),
                type="circle",
                delay_show=200,          # don't flash the spinner on memoised (instant) results
                delay_hide=100,
                overlay_style={"visibility": "visible", "opacity": 0.45},
            ),
        ],
    )


@memo.keyed_memo(maxsize=192)
def render_analytics_tab_content(country_code: str, tab: str, year: int, province: str, municipality_id: str, metric_id: str, dark: bool) -> html.Div:
    """Builds the content of the active analytics tab. Called by the analytics
    callback. Memoised: within a data release each argument combination has a
    single answer, so a revisited selection or tab is a dict lookup."""
    country = constants.COUNTRY_BY_CODE[country_code]
    admin = country["admin_labels"]
    page_data = queries.get_analytics_page_data(
        country_code, year=year, province=province, municipality_id=municipality_id,
        metric_id=metric_id, x_metric_id=constants.DEFAULT_SCATTER_X_METRIC_ID, y_metric_id=constants.DEFAULT_SCATTER_Y_METRIC_ID,
        sections={tab or "map"},
    )

    if tab == "map":
        fig = utils.build_choropleth_figure(
            page_data["map"]["features"], page_data["map"]["metric"]["label"],
            page_data["map"]["summary"]["minimum"], page_data["map"]["summary"]["maximum"], admin, dark=dark,
        )
        return html.Section(className="section-card", children=[
            html.P("Choropleth map", className="eyebrow"),
            html.H2(page_data["map"]["metric"]["label"]),
            html.P(page_data["map"]["coverageLabel"], className="small muted"),
            html.Div(className="dash-graph", children=utils.wrap_chart(fig, "analytics-map-graph")),
        ])

    if tab == "scatter2d":
        fig = utils.build_scatter2d_figure(
            page_data["scatter2d"]["points"], page_data["scatter2d"]["xMetric"]["label"], page_data["scatter2d"]["yMetric"]["label"],
            province, admin, dark=dark,
        )
        return html.Section(className="section-card", children=[
            html.P("2D scatterplot", className="eyebrow"),
            html.H2(f"{page_data['scatter2d']['yMetric']['label']} vs {page_data['scatter2d']['xMetric']['label']}"),
            html.P(f"Hover for score values, drag to zoom. Highlighted {utils.lower_first(admin['lower']['singular'])}: {page_data['selected']['municipalityName']}.", className="small muted"),
            html.Div(className="dash-graph", children=utils.wrap_chart(fig, "analytics-scatter2d-graph")),
        ])

    if tab == "scatter3d":
        fig = utils.build_scatter3d_figure(page_data["scatter3d"]["points"], dark=dark)
        return html.Section(className="section-card", children=[
            html.P("3D scatterplot", className="eyebrow"),
            html.H2("Prosperity vs Infrastructure vs Livability"),
            html.Div(className="dash-graph", children=utils.wrap_chart(fig, "analytics-scatter3d-graph")),
        ])

    # drivers
    groups = page_data["waterfalls"]
    blocks = []
    for group in groups:
        fig = utils.build_waterfall_figure(group, dark=dark)
        blocks.append(html.Section(className="section-card", children=[
            html.P("Waterfall chart", className="eyebrow"),
            html.H2(group["scoreLabel"]),
            html.P(f"Selected {utils.lower_first(admin['lower']['singular'])}: {page_data['municipality']['municipality']}, "
                   f"{admin['higher']['singular']}: {page_data['municipality']['province']}", style={"fontWeight": 600}),
            utils.waterfall_summary_block(group),
            html.Div(className="dash-graph", children=utils.wrap_chart(fig, f"analytics-waterfall-{group['scoreId']}")),
        ]))
    return html.Div(blocks)


# ==========================================================================
# STRATEGY INVENTORY PAGE - port of
# src/components/strategy-inventory/strategy-inventory-dashboard.tsx
# ==========================================================================

def render_strategy_inventory(slug: str) -> html.Main:
    country = constants.COUNTRY_BY_SLUG.get(slug)
    if not country or slug not in constants.STRATEGY_INVENTORY_SLUGS:
        return render_not_found()

    dataset = queries.get_strategy_inventory_dataset(country["code"])
    if not dataset:
        return html.Main(className="page-container", children=[
            html.H1(f"{country['name']} strategy inventory"),
            html.P("No strategy inventory dataset is currently loaded for this country."),
        ])

    return html.Main(
        className="page-container",
        children=[
            dcc.Store(id="strategy-country-store", data=country["code"]),
            html.Section(children=[
                html.P(f"{country['name']} strategy inventory", className="eyebrow"),
                html.H1("Local strategy document tracking"),
                html.P(
                    f"Tracks local development strategy and budget document availability, "
                    f"AI readiness, and follow-up needs across {country['name']}'s "
                    f"{utils.lower_first(country['admin_labels']['lower']['plural'])}.",
                    className="lede",
                ),
                (html.P("Sample / preview dataset - replace with validated source metadata before use in decision-making.", className="badge badge-outline")
                 if dataset.get("is_sample_data") else None),
            ]),
            html.Div(id="strategy-summary-cards", style={"marginTop": "1.5rem"}),
            html.Div(className="filters-card", children=[
                html.Div(className="filters-grid", children=[
                    html.Div(className="filter-field", children=[html.Label("Search"), dcc.Input(id="strategy-search", type="text", placeholder="Search by LSG name...", style={"width": "100%", "height": "2.25rem", "borderRadius": "0.5rem", "border": "1px solid var(--border-soft)"})]),
                    html.Div(className="filter-field", children=[
                        html.Label("Readiness"),
                        dcc.Dropdown(id="strategy-readiness", options=[{"label": "All", "value": "all"}] + [{"label": c, "value": c} for c in constants.READINESS_CATEGORIES], value="all", clearable=False),
                    ]),
                    html.Div(className="filter-field", children=[
                        html.Label("Document type"),
                        dcc.Dropdown(id="strategy-doctype", options=[{"label": "All", "value": "all"}] + [{"label": t.title(), "value": t} for t in constants.DOCUMENT_TYPES], value="all", clearable=False),
                    ]),
                    html.Div(className="filter-field", children=[
                        html.Label("Translation status"),
                        dcc.Dropdown(id="strategy-translation", options=[{"label": "All", "value": "all"}] + [{"label": t.replace("_", " ").title(), "value": t} for t in constants.TRANSLATION_STATUSES], value="all", clearable=False),
                    ]),
                ]),
            ]),
            dcc.Loading(
                type="circle",
                delay_show=200,
                children=[
                    html.Div(className="grid-2", style={"marginTop": "1.5rem"}, children=[
                        html.Div(id="strategy-readiness-chart"),
                        html.Div(id="strategy-year-chart"),
                    ]),
                    html.Div(id="strategy-table", style={"marginTop": "1.5rem"}),
                ],
            ),
        ],
    )


def build_strategy_summary_cards(summary: Dict[str, Any]) -> html.Div:
    tiles = [
        ("LSG coverage", f"{summary['coverage_rate'] * 100:.0f}%", f"{summary['lsgs_with_any_document']} of {summary['expected_lsgs']} LSGs"),
        ("Documents found", str(summary["total_documents_found"]), f"{summary['strategies_found']} strategies \u2022 {summary['budgets_found']} budgets"),
        ("AI-ready documents", str(summary["ai_ready_documents"]), "Parsed and ready for AI-assisted analysis"),
        ("Needs attention", str(summary["needs_translation"] + summary["needs_validation"]), f"{summary['needs_translation']} translation \u2022 {summary['needs_validation']} validation"),
    ]
    return html.Div(className="summary-stat-grid", children=[
        html.Div(className="summary-stat", children=[html.P(title, className="eyebrow"), html.P(value, className="value"), html.P(sub, className="small muted")])
        for title, value, sub in tiles
    ])


def build_strategy_table(records: List[Dict[str, Any]], limit: int = 50) -> html.Div:
    header = ["LSG", "Region", "Document type", "Title", "Year", "Readiness", "Language", "Last updated"]
    rows = []
    for r in records[:limit]:
        rows.append(html.Tr([
            html.Td(r.get("lsg_name", "")), html.Td(r.get("region_name", "")),
            html.Td((r.get("document_type") or "").title()), html.Td(r.get("document_title") or "\u2014"),
            html.Td(r.get("publication_year") or "\u2014"),
            html.Td(html.Span(queries.get_readiness_category(r), className="badge badge-outline", style={"borderColor": constants.READINESS_COLORS.get(queries.get_readiness_category(r))})),
            html.Td((r.get("language") or "unknown")), html.Td(r.get("last_updated") or "\u2014"),
        ]))
    return html.Div(children=[
        html.Div(className="ldt-table-wrap", children=html.Table(className="ldt-table", children=[html.Thead(html.Tr([html.Th(h) for h in header])), html.Tbody(rows)])),
        html.P(f"Showing {min(limit, len(records))} of {len(records)} matching records.", className="small muted", style={"marginTop": "0.5rem"}),
    ])


# ==========================================================================
# ROUTING
# ==========================================================================

STATIC_ROUTES = {
    "home": render_home,
    "about": render_about,
    "methodology": render_methodology,
    "roadmap": render_roadmap,
    "resources": render_resources,
    "release-notes": render_release_notes,
}


def parse_page_query(search: str) -> Dict[str, str]:
    """Parses a ``?page=nepal&view=analytics``-style query string.

    Every route in the app is addressed through query parameters instead of
    path segments, e.g.:

        /?page=home
        /?page=about
        /?page=nepal
        /?page=nepal&view=analytics
        /?page=nepal&view=strategy-inventory

    This keeps every internal link a plain relative ``?page=...`` href, so
    the app can be mounted at any base path (e.g. behind a reverse proxy at
    ``) with no link rewriting required.
    """
    search = search or ""
    qs = parse_qs(search.lstrip("?"))
    page = (qs.get("page", ["home"])[0] or "home").strip()
    view = (qs.get("view", [""])[0] or "").strip()
    return {"page": page, "view": view}


def build_route_content(search: str) -> html.Main:
    route = parse_page_query(search)
    page, view = route["page"], route["view"]
    logger.debug("Resolving route: page=%s view=%s", page, view)

    if not view and page in STATIC_ROUTES:
        return STATIC_ROUTES[page]()

    if page in constants.COUNTRY_BY_SLUG:
        if view == "analytics":
            return render_analytics(page)
        if view == "strategy-inventory":
            return render_strategy_inventory(page)
        if not view:
            return render_country_landing(page)

    return render_not_found()


@app.callback(
    Output("ldt-page-content", "children"),
    Output("ldt-header-slot", "children"),
    Output("ldt-footer-slot", "children"),
    Input("url", "search"),
)
def render_page_content(search):
    logger.debug("Rendering page shell for query %s", search)
    current_page = parse_page_query(search)["page"]
    try:
        content = build_route_content(search)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed while rendering page content for %s.", search)
        content = render_error(str(exc))
    return content, utils.app_header(current_page), utils.app_footer()


# ==========================================================================
# THEME + MOBILE NAV CALLBACKS
# ==========================================================================

app.clientside_callback(
    """
    function(themeData) {
        const theme = (themeData && themeData.theme) || 'light';
        document.documentElement.setAttribute('data-theme', theme);
        return '';
    }
    """,
    Output("theme-applier", "title"),
    Input("theme-store", "data"),
)


@app.callback(
    Output("theme-store", "data"),
    Input("theme-toggle-button", "n_clicks"),
    State("theme-store", "data"),
    prevent_initial_call=True,
)
def toggle_theme(n_clicks, current):
    current = current or {"theme": "light"}
    next_theme = "dark" if current.get("theme") == "light" else "light"
    return {"theme": next_theme}


app.clientside_callback(
    """
    function(n_clicks) {
        if (!n_clicks) { return window.dash_clientside.no_update; }
        const panel = document.getElementById('mobile-nav-panel');
        if (panel) { panel.classList.toggle('hidden'); }
        return window.dash_clientside.no_update;
    }
    """,
    Output("mobile-nav-toggle", "title"),
    Input("mobile-nav-toggle", "n_clicks"),
    prevent_initial_call=True,
)


# ==========================================================================
# HOME PAGE - country selector
# ==========================================================================

app.clientside_callback(
    """
    function(n_clicks, slug) {
        if (!n_clicks || !slug) { return window.dash_clientside.no_update; }
        return '?page=' + slug;
    }
    """,
    Output("url", "search"),
    Input("home-country-open", "n_clicks"),
    State("home-country-select", "value"),
    prevent_initial_call=True,
)


# ==========================================================================
# ANALYTICS PAGE CALLBACKS
# ==========================================================================

@app.callback(
    Output("analytics-municipality", "options"),
    Output("analytics-municipality", "value"),
    Input("analytics-year", "value"),
    Input("analytics-province", "value"),
    State("analytics-country-store", "data"),
    State("analytics-municipality", "value"),
    prevent_initial_call=True,
)
def update_municipality_options(year, province, country_code, current_municipality_id):
    if not country_code:
        raise PreventUpdate
    logger.debug("Updating municipality options for %s year=%s province=%s", country_code, year, province)
    try:
        options = [{"label": o["label"], "value": o["id"]} for o in queries.get_municipality_options(country_code, year, province)]
        ids = {o["value"] for o in options}
        value = current_municipality_id if current_municipality_id in ids else (options[0]["value"] if options else None)
        return options, value
    except Exception:
        logger.exception("Municipality dropdown update failed for %s %s %s.", country_code, year, province)
        raise


@app.callback(
    Output("analytics-tab-content", "children"),
    Input("analytics-tabs", "value"),
    Input("analytics-year", "value"),
    Input("analytics-province", "value"),
    Input("analytics-municipality", "value"),
    Input("analytics-metric", "value"),
    Input("theme-store", "data"),
    State("analytics-country-store", "data"),
)
def update_analytics_tab(tab, year, province, municipality_id, metric_id, theme_data, country_code):
    if not country_code:
        raise PreventUpdate
    dark = (theme_data or {}).get("theme") == "dark"
    logger.debug("Updating analytics tab %s for %s (year=%s, province=%s, municipality=%s)", tab, country_code, year, province, municipality_id)
    try:
        return render_analytics_tab_content(country_code, tab, year, province, municipality_id, metric_id, dark)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Analytics tab render failed for country=%s tab=%s.", country_code, tab)
        return html.Section(className="section-card", children=[
            html.H2("Data temporarily unavailable"),
            html.P("Could not load analytics data from Databricks. Try again shortly."),
            html.P(str(exc), className="small muted"),
        ])


@app.callback(
    Output("sng-csv-download", "data"),
    Input({"type": "sng-csv-button", "country": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def download_sng_csv(n_clicks_list):
    triggered = callback_context.triggered_id
    if not triggered or not any(n_clicks_list):
        raise PreventUpdate

    country_slug = triggered["country"]
    country = constants.COUNTRY_BY_SLUG.get(country_slug)
    if not country:
        raise PreventUpdate

    logger.debug("Exporting CSV for %s country data.", country_slug)
    try:
        dataset = queries.load_country_dataset(country["code"])
        latest_year = max(dataset.get("years", [dataset.get("release", {}).get("year", 0)]))
        rows = [m for m in dataset["municipalities"] if m["year"] == latest_year]

        df = pd.DataFrame([
            {
                country["admin_labels"]["lower"]["singular"]: m["municipality"],
                country["admin_labels"]["higher"]["singular"]: m["province"],
                "Population": m["context"].get("population"),
                "Area (km2)": m["context"].get("totalLandAreaKm2"),
                "Infrastructure score": m["scores"].get("infrastructure_score"),
                "Livability score": m["scores"].get("livability_score"),
                "Prosperity score": m["scores"].get("prosperity_score"),
            }
            for m in rows
        ])

        filename = f"{country['slug']}-sng-{utils.lower_first(country['admin_labels']['lower']['singular'])}-metrics.csv"
        return dcc.send_data_frame(df.to_csv, filename, index=False)
    except Exception:
        logger.exception("CSV export failed for country %s.", country_slug)
        raise


# ==========================================================================
# STRATEGY INVENTORY CALLBACKS
# ==========================================================================

@memo.keyed_memo(maxsize=16)
def _strategy_static_blocks(country_code: str, dark: bool):
    """Summary cards + the two overview charts. None of these depend on the
    search / filter inputs, so they are computed once per (country, theme)
    and replayed while the user types."""
    dataset = queries.get_strategy_inventory_dataset(country_code)
    if not dataset:
        return None
    summary = queries.get_strategy_inventory_summary(
        dataset["records"], dataset["expected_lsg_count"], dataset.get("summary_override")
    )
    readiness_fig = utils.build_readiness_bar_chart(summary["status_breakdown"], dark=dark)
    year_fig = utils.build_publication_year_chart(summary["publication_year_counts"], dark=dark)
    return (
        build_strategy_summary_cards(summary),
        html.Div(className="content-card", children=[html.H3("Readiness breakdown"), utils.wrap_chart(readiness_fig, "strategy-readiness-graph")]),
        html.Div(className="content-card", children=[html.H3("Documents by publication year"), utils.wrap_chart(year_fig, "strategy-year-graph")]),
    )


@app.callback(
    Output("strategy-summary-cards", "children"),
    Output("strategy-readiness-chart", "children"),
    Output("strategy-year-chart", "children"),
    Output("strategy-table", "children"),
    Input("strategy-search", "value"),
    Input("strategy-readiness", "value"),
    Input("strategy-doctype", "value"),
    Input("strategy-translation", "value"),
    Input("theme-store", "data"),
    State("strategy-country-store", "data"),
)
def update_strategy_inventory(search, readiness, doctype, translation, theme_data, country_code):
    if not country_code:
        raise PreventUpdate

    logger.debug("Refreshing strategy inventory for %s.", country_code)
    try:
        dataset = queries.get_strategy_inventory_dataset(country_code)
        if not dataset:
            raise PreventUpdate

        dark = (theme_data or {}).get("theme") == "dark"
        static_blocks = _strategy_static_blocks(country_code, dark)
        if static_blocks is None:
            raise PreventUpdate
        summary_cards, readiness_block, year_block = static_blocks

        all_records = dataset["records"]
        filtered = all_records
        if search:
            needle = search.strip().lower()
            filtered = [r for r in filtered if needle in (r.get("lsg_name") or "").lower()]
        if readiness and readiness != "all":
            filtered = [r for r in filtered if queries.get_readiness_category(r) == readiness]
        if doctype and doctype != "all":
            filtered = [r for r in filtered if r.get("document_type") == doctype]
        if translation and translation != "all":
            filtered = [r for r in filtered if r.get("translation_status") == translation]

        table = build_strategy_table(filtered)

        return (summary_cards, readiness_block, year_block, table)
    except Exception:
        logger.exception("Strategy inventory refresh failed for %s.", country_code)
        raise


# --------------------------------------------------------------------------
# Local dev entrypoint. Production servers (e.g. Posit Connect / gunicorn)
# should import `server` from this module instead of running this block -
# see README.md for deployment instructions.
# --------------------------------------------------------------------------

if __name__ == "__main__":
    debug = os.environ.get("DASH_DEBUG", "true").lower() == "true"
    port = int(os.environ.get("PORT", "3000"))
    logger.info("Starting Dash server with debug=%s on port %s.", debug, port)

    run = getattr(app, "run", None) or app.run_server
    run(debug=debug, host="127.0.0.1", port=port)