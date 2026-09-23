"""
utils.py
================
Visualization functions and reusable UI-component "toolkit" for the Local
Development Tracker Dash app.

Two kinds of helpers live here:
  1. Chart builders (Plotly figures) - ports of the logic in
     src/components/analytics/{choropleth-map,scatter-2d,scatter-3d,
     score-waterfall-section,score-driver-chart}.tsx
  2. Dash component builders (header, footer, cards, badges, figure
     cards, section cards, etc.) - ports of the small presentational
     components under src/components/layout and the *Card patterns
     repeated throughout the Next.js pages.

Nothing here reads from a database; all data comes in as plain arguments
so these functions stay easy to unit test and reuse across pages.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import dash
import plotly.graph_objects as go
from dash import dcc, html

import constants

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Small string helpers
# --------------------------------------------------------------------------

def lower_first(value: str) -> str:
    if not value:
        return value
    return value[0].lower() + value[1:]


def fmt(value: Optional[float], digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


# --------------------------------------------------------------------------
# Layout / chrome components (src/components/layout/*)
# --------------------------------------------------------------------------

def page_param(href: str) -> str:
    """Extracts the ``page`` query-param value from a ``?page=...`` href.

    All internal navigation is done through query-string routing
    (``?page=nepal``, ``?page=nepal&view=analytics``, ...) rather than path
    segments, so "which nav item is active" is decided by comparing the
    ``page`` param, not the URL path.
    """
    query = urlparse(href).query
    return parse_qs(query).get("page", [""])[0]


def is_active_page(current_page: str, href: str, exact: bool = False) -> bool:
    if "#" in href:
        return False
    target = page_param(href)
    if not target:
        return False
    if exact:
        return current_page == target
    return current_page == target or current_page.startswith(target + "-")


def nav_link(item: Dict[str, Any], current_page: str, class_prefix: str = "chrome-nav-link") -> html.A:
    active = is_active_page(current_page, item["href"], item.get("exact", False))
    classes = class_prefix + (" active" if active else "")
    return html.A(item["label"], href=item["href"], className=classes)


def app_header(current_page: str = "home") -> html.Header:
    """Port of src/components/layout/app-header.tsx"""
    nav_links = [nav_link(item, current_page) for item in constants.HEADER_NAV_ITEMS]

    return html.Header(
        className="ldt-header",
        children=[
            html.Div(
                className="ldt-header-inner",
                children=[
                    html.A(
                        href="?page=home",
                        className="ldt-header-logo",
                        children=html.Img(src=dash.get_asset_url("ldt-logo-dark.png"), alt="Local Development Tracker"),
                    ),
                    html.Nav(className="ldt-header-nav", children=nav_links),
                    html.Div(
                        className="ldt-header-actions",
                        children=[
                            # html.Span(
                            #     className="ldt-lang-indicator",
                            #     children=["\U0001F310 EN"],
                            # ),
                            # html.Button(
                            #     "\u2600\ufe0f / \U0001F319",
                            #     id="theme-toggle-button",
                            #     className="ldt-theme-toggle",
                            #     n_clicks=0,
                            #     title="Toggle light / dark mode",
                            # ),
                            # html.A(
                            #     "Part of the GPB Suite",
                            #     href="https://pim-pam.net/web-applications/#gpbp",
                            #     target="_blank",
                            #     className="ldt-gpb-badge",
                            # ),
                            html.Button(
                                "\u2630",
                                id="mobile-nav-toggle",
                                className="ldt-mobile-nav-toggle",
                                n_clicks=0,
                                title="Open navigation",
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(id="mobile-nav-panel", className="ldt-mobile-nav-panel hidden", children=nav_links),
        ],
    )


def app_footer() -> html.Footer:
    """Port of src/components/layout/site-footer.tsx"""
    return html.Footer(
        className="ldt-footer",
        children=html.Div(
            className="ldt-footer-inner",
            children=[
                html.Section(
                    className="ldt-footer-brand",
                    children=[
                        html.A(
                            href="?page=home",
                            children=html.Img(src=dash.get_asset_url("ldt-logo-dark.png"), alt="Local Development Tracker", className="ldt-footer-logo"),
                        ),
                        html.P(
                            "Municipality-level analytics for comparing local development "
                            "conditions, reading score drivers, and connecting planning "
                            "evidence to public investment decisions."
                        ),
                    ],
                ),
                html.Nav(
                    className="ldt-footer-nav",
                    children=[
                        html.H2("Explore"),
                        html.Ul([html.Li(html.A(item["label"], href=item["href"])) for item in constants.FOOTER_NAV_ITEMS]),
                    ],
                ),
                html.Nav(
                    className="ldt-footer-nav",
                    children=[
                        html.H2("Countries"),
                        html.Ul([html.Li(html.A(item["label"], href=item["href"])) for item in constants.COUNTRY_WORKSPACE_LINKS]),
                    ],
                ),
                # html.Section(
                #     className="ldt-footer-branding",
                #     children=[
                #         # html.A(
                #         #     "Part of the GPB Suite",
                #         #     href="https://pim-pam.net/web-applications/#gpbp",
                #         #     target="_blank",
                #         #     className="ldt-gpb-badge",
                #         # ),
                #         html.A(
                #             html.Img(src="/assets/pimpam_logo.png", alt="PIM PAM"),
                #             href="https://pim-pam.net/",
                #             target="_blank",
                #             className="ldt-pimpam-plate",
                #         ),
                #     ],
                # ),
            ],
        ),
    )


def ecosystem_logo_grid() -> html.Div:
    return html.Div(
        className="ldt-ecosystem-grid",
        children=[
            html.A(
                html.Img(src=dash.get_asset_url("gpb-logo.png"), alt="GPB Tools"),
                href="https://pim-pam.net/web-applications/#gpbp",
                target="_blank",
                className="ldt-ecosystem-tile",
            ),
            html.A(
                html.Img(src=dash.get_asset_url("pimpam_logo.png"), alt="PIM PAM"),
                href="https://pim-pam.net/",
                target="_blank",
                className="ldt-ecosystem-tile",
            ),
        ],
    )


# --------------------------------------------------------------------------
# Generic presentational building blocks
# --------------------------------------------------------------------------

def page_header(eyebrow: str, title: str, body: Optional[str] = None, meta: Optional[str] = None) -> html.Section:
    children = [html.P(eyebrow, className="eyebrow")]
    children.append(html.H1(title))
    if meta:
        children.append(html.P(meta, className="page-meta"))
    if body:
        children.append(html.P(body, className="lede"))
    return html.Section(className="page-hero-card", children=children)


def section_card(title: str, children, eyebrow: Optional[str] = None, className: str = "") -> html.Section:
    header_children = []
    if eyebrow:
        header_children.append(html.P(eyebrow, className="eyebrow"))
    header_children.append(html.H2(title))
    return html.Section(
        className=f"section-card {className}".strip(),
        children=header_children + (children if isinstance(children, list) else [children]),
    )


def figure_card(src: str, alt: str, caption: str) -> html.Figure:
    return html.Figure(
        className="figure-card",
        children=[
            html.Img(src=dash.get_asset_url(src), alt=alt),
            html.Figcaption(caption),
        ],
    )


def stat_card(value: str, label: str) -> html.Div:
    return html.Div(className="stat-card", children=[html.P(value, className="stat-value"), html.P(label, className="stat-label")])


def capability_card(title: str, body: str) -> html.Div:
    return html.Div(className="capability-card", children=[html.H2(title), html.P(body)])


def badge(text: str, variant: str = "outline") -> html.Span:
    return html.Span(text, className=f"badge badge-{variant}")


def link_button(label: str, href: str, variant: str = "secondary") -> html.A:
    return html.A(label, href=href, className=f"ldt-action-button {variant}")


# --------------------------------------------------------------------------
# Chart builders - choropleth (src/components/analytics/choropleth-map.tsx)
# --------------------------------------------------------------------------

def build_choropleth_figure(
    features: List[Dict[str, Any]],
    metric_label: str,
    minimum: Optional[float],
    maximum: Optional[float],
    admin_labels: Dict[str, Any],
    dark: bool = False,
) -> go.Figure:
    """
    Renders the municipality choropleth using Plotly's Choroplethmapbox,
    replicating the min -> max color ramp used by the MapLibre version
    (`#e5ebf8` -> `#3675b7`, with `#e7e7e7` for missing data).
    """
    logger.debug("Building choropleth figure for %s features (%s)", len(features), metric_label)
    colors = constants.COLORS_DARK if dark else constants.COLORS_LIGHT

    if not features:
        fig = go.Figure()
        fig.update_layout(
            paper_bgcolor=colors["chart_surface"],
            plot_bgcolor=colors["chart_surface"],
            annotations=[{
                "text": "No boundary data available for this selection.",
                "showarrow": False,
                "font": {"color": colors["chart_text"]},
            }],
            margin=dict(l=0, r=0, t=10, b=0),
            height=520,
        )
        return fig

    geojson = {"type": "FeatureCollection", "features": features}
    location_ids = [f["properties"]["compositeKey"] for f in features]
    values = [f.get("metricValue") for f in features]
    hover_names = [f["properties"].get("Municipality", "") for f in features]

    if admin_labels.get("middle"):
        hover_extra = [
            f"{admin_labels['middle']['singular']}: {f['properties'].get('District', '')}<br>"
            f"{admin_labels['higher']['singular']}: {f['properties'].get('Province', '')}"
            for f in features
        ]
    else:
        hover_extra = [f"{admin_labels['higher']['singular']}: {f['properties'].get('Province', '')}" for f in features]

    zmin = minimum if minimum is not None else 0
    zmax = maximum if maximum is not None and maximum > (minimum or 0) else zmin + 1

    fig = go.Figure(
        go.Choroplethmapbox(
            geojson=geojson,
            locations=location_ids,
            z=values,
            featureidkey="properties.compositeKey",
            colorscale=[[0, colors["map_min"]], [1, colors["map_max"]]],
            zmin=zmin,
            zmax=zmax,
            marker_line_width=0.6,
            marker_line_color="rgba(2,20,32,0.35)" if not dark else "rgba(201,211,234,0.35)",
            colorbar=dict(title=metric_label, thickness=14, len=0.75),
            customdata=list(zip(hover_names, hover_extra)),
            hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<br>" + metric_label + ": %{z:.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        map=dict(style="carto-darkmatter" if dark else "carto-positron", zoom=5.2, center=_map_center(features)),
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor=colors["chart_surface"],
        height=560,
    )
    return fig


def _map_center(features: List[Dict[str, Any]]) -> Dict[str, float]:
    lats, lons = [], []

    def walk(coords):
        if not coords:
            return
        if isinstance(coords[0], (int, float)):
            lons.append(coords[0])
            lats.append(coords[1])
            return
        for part in coords:
            walk(part)

    for feature in features[:200]:  # sample for performance
        geometry = feature.get("geometry", {})
        walk(geometry.get("coordinates"))

    if not lats:
        return {"lat": 0, "lon": 0}
    return {"lat": sum(lats) / len(lats), "lon": sum(lons) / len(lons)}


# --------------------------------------------------------------------------
# Chart builders - 2D scatter (src/components/analytics/scatter-2d.tsx)
# --------------------------------------------------------------------------

def build_scatter2d_figure(
    points: List[Dict[str, Any]],
    x_label: str,
    y_label: str,
    selected_province: str,
    admin_labels: Dict[str, Any],
    dark: bool = False,
) -> go.Figure:
    logger.debug("Building scatter2d figure for %s points (%s vs %s)", len(points), x_label, y_label)
    colors = constants.COLORS_DARK if dark else constants.COLORS_LIGHT
    visible = [p for p in points if p["x"] is not None and p["y"] is not None]
    highlighted = [p for p in visible if p["selected"]]
    same_province = [p for p in visible if not p["selected"] and p["province"] == selected_province]
    others = [p for p in visible if not p["selected"] and p["province"] != selected_province]

    lower_plural = lower_first(admin_labels["lower"]["plural"])
    higher_singular = admin_labels["higher"]["singular"]

    def location_text(p):
        if admin_labels.get("middle"):
            return f"{admin_labels['middle']['singular']}: {p['district']}<br>{higher_singular}: {p['province']}<br>"
        return f"{higher_singular}: {p['province']}<br>"

    def trace(rows, name, color, size, line=None):
        return go.Scatter(
            x=[r["x"] for r in rows],
            y=[r["y"] for r in rows],
            mode="markers",
            name=name,
            text=[r["label"] for r in rows],
            customdata=[[r["district"], r["province"]] for r in rows],
            marker=dict(color=color, size=size, line=line),
            hovertemplate=(
                "<b>%{text}</b><br>"
                + (f"{admin_labels['middle']['singular']}: %{{customdata[0]}}<br>" if admin_labels.get("middle") else "")
                + f"{higher_singular}: %{{customdata[1]}}<br>"
                + f"{x_label}: %{{x:.2f}}<br>{y_label}: %{{y:.2f}}<extra></extra>"
            ),
        )

    fig = go.Figure()
    fig.add_trace(trace(others, f"Other {lower_plural}", colors["chart_muted_series"], 7))
    fig.add_trace(trace(same_province, f"Same {lower_first(higher_singular)}", "#f4a261", 9, line=dict(color="#9a4d00", width=0.6)))
    fig.add_trace(trace(highlighted, "Highlighted", colors["chart_1"], 13, line=dict(color=colors["foreground"] if dark else "#1c2a5e", width=1.2)))

    fig.update_layout(
        template="plotly_dark" if dark else "plotly_white",
        paper_bgcolor=colors["chart_surface"],
        plot_bgcolor=colors["chart_surface"],
        font=dict(color=colors["chart_text"]),
        xaxis=dict(title=x_label, gridcolor=colors["chart_grid"], zerolinecolor=colors["chart_axis"], color=colors["chart_tick"]),
        yaxis=dict(title=y_label, gridcolor=colors["chart_grid"], zerolinecolor=colors["chart_axis"], color=colors["chart_tick"]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        margin=dict(l=10, r=10, t=10, b=10),
        height=520,
    )
    return fig


# --------------------------------------------------------------------------
# Chart builders - 3D scatter (src/components/analytics/scatter-3d.tsx)
# --------------------------------------------------------------------------

def build_scatter3d_figure(points: List[Dict[str, Any]], dark: bool = False) -> go.Figure:
    logger.debug("Building scatter3d figure for %s points", len(points))
    colors = constants.COLORS_DARK if dark else constants.COLORS_LIGHT
    visible = [p for p in points if p["x"] is not None and p["y"] is not None and p["z"] is not None]
    highlighted = [p for p in visible if p["selected"]]
    others = [p for p in visible if not p["selected"]]

    def trace(rows, name, color, size):
        return go.Scatter3d(
            x=[r["x"] for r in rows],
            y=[r["y"] for r in rows],
            z=[r["z"] for r in rows],
            mode="markers",
            name=name,
            text=[r["label"] for r in rows],
            marker=dict(color=color, size=size),
            hovertemplate="<b>%{text}</b><br>Prosperity: %{x:.2f}<br>Infrastructure: %{y:.2f}<br>Livability: %{z:.2f}<extra></extra>",
        )

    fig = go.Figure()
    fig.add_trace(trace(others, "Municipalities", colors["chart_muted_series"], 4))
    fig.add_trace(trace(highlighted, "Highlighted", colors["chart_1"], 7))
    fig.update_layout(
        template="plotly_dark" if dark else "plotly_white",
        paper_bgcolor=colors["chart_surface"],
        scene=dict(
            xaxis=dict(title="Prosperity score", color=colors["chart_tick"], gridcolor=colors["chart_grid"]),
            yaxis=dict(title="Infrastructure score", color=colors["chart_tick"], gridcolor=colors["chart_grid"]),
            zaxis=dict(title="Livability score", color=colors["chart_tick"], gridcolor=colors["chart_grid"]),
            bgcolor=colors["chart_surface"],
        ),
        margin=dict(l=0, r=0, t=10, b=0),
        height=600,
        font=dict(color=colors["chart_text"]),
    )
    return fig


# --------------------------------------------------------------------------
# Chart builders - score-driver waterfall
# (src/components/analytics/score-waterfall-section.tsx)
# --------------------------------------------------------------------------

def build_waterfall_figure(group: Dict[str, Any], dark: bool = False) -> go.Figure:
    logger.debug("Building waterfall chart for %s", group.get("scoreLabel", "unknown"))
    colors = constants.COLORS_DARK if dark else constants.COLORS_LIGHT
    rows = [r for r in group["rows"] if r["contribution"] is not None]
    rows = sorted(rows, key=lambda r: r["contribution"])

    labels = [r["label"].replace(" Score", "") for r in rows]
    contributions = [r["contribution"] for r in rows]
    bar_colors = [colors["positive"] if c >= 0 else colors["negative"] for c in contributions]
    text = [f"{'+' if c >= 0 else ''}{c:.2f}" for c in contributions]

    fig = go.Figure(
        go.Bar(
            x=contributions,
            y=labels,
            orientation="h",
            marker_color=bar_colors,
            text=text,
            textposition="outside",
            hovertemplate="%{y}<br>Contribution: %{x:.2f} points<extra></extra>",
        )
    )
    fig.add_vline(x=0, line_width=1, line_color=colors["chart_axis"])
    fig.update_layout(
        template="plotly_dark" if dark else "plotly_white",
        paper_bgcolor=colors["chart_surface"],
        plot_bgcolor=colors["chart_surface"],
        font=dict(color=colors["chart_text"]),
        xaxis=dict(title="Impact on score (vs. country average)", gridcolor=colors["chart_grid"], zeroline=False, color=colors["chart_tick"]),
        yaxis=dict(gridcolor=colors["chart_grid"], color=colors["chart_tick"]),
        margin=dict(l=10, r=40, t=10, b=10),
        height=max(320, 46 * len(rows)),
        showlegend=False,
    )
    return fig


def waterfall_summary_block(group: Dict[str, Any]) -> html.Div:
    diff = group["totalDifference"]
    diff_class = "positive" if (diff or 0) >= 0 else "negative"
    diff_text = f"{'+' if diff is not None and diff >= 0 else ''}{fmt(diff)} points" if diff is not None else "n/a"
    return html.Div(
        className="waterfall-summary",
        children=[
            html.P(f"{group['scoreLabel']}: {fmt(group['municipalityScore'])}", className="waterfall-score"),
            html.P([
                f"Country average: {fmt(group['nationalScore'])} | Difference: ",
                html.Span(diff_text, className=f"waterfall-diff {diff_class}"),
            ]),
        ],
    )


# --------------------------------------------------------------------------
# Chart builders - strategy inventory readiness bar chart
# --------------------------------------------------------------------------

def build_readiness_bar_chart(status_breakdown: List[Dict[str, Any]], dark: bool = False) -> go.Figure:
    logger.debug("Building readiness chart for %s categories", len(status_breakdown))
    colors = constants.COLORS_DARK if dark else constants.COLORS_LIGHT
    categories = [row["category"] for row in status_breakdown]
    counts = [row["count"] for row in status_breakdown]
    bar_colors = [constants.READINESS_COLORS.get(c, colors["chart_1"]) for c in categories]

    fig = go.Figure(
        go.Bar(x=categories, y=counts, marker_color=bar_colors, text=counts, textposition="outside")
    )
    fig.update_layout(
        template="plotly_dark" if dark else "plotly_white",
        paper_bgcolor=colors["chart_surface"],
        plot_bgcolor=colors["chart_surface"],
        font=dict(color=colors["chart_text"]),
        xaxis=dict(color=colors["chart_tick"]),
        yaxis=dict(title="Documents", gridcolor=colors["chart_grid"], color=colors["chart_tick"]),
        margin=dict(l=10, r=10, t=20, b=10),
        height=360,
        showlegend=False,
    )
    return fig


def build_publication_year_chart(year_counts: List[Dict[str, Any]], dark: bool = False) -> go.Figure:
    logger.debug("Building publication-year chart for %s entries", len(year_counts))
    colors = constants.COLORS_DARK if dark else constants.COLORS_LIGHT
    years = [row["year"] for row in year_counts]
    counts = [row["count"] for row in year_counts]

    fig = go.Figure(go.Bar(x=years, y=counts, marker_color=colors["chart_1"], text=counts, textposition="outside"))
    fig.update_layout(
        template="plotly_dark" if dark else "plotly_white",
        paper_bgcolor=colors["chart_surface"],
        plot_bgcolor=colors["chart_surface"],
        font=dict(color=colors["chart_text"]),
        xaxis=dict(title="Publication year", color=colors["chart_tick"]),
        yaxis=dict(title="Documents", gridcolor=colors["chart_grid"], color=colors["chart_tick"]),
        margin=dict(l=10, r=10, t=20, b=10),
        height=320,
        showlegend=False,
    )
    return fig


def wrap_chart(figure: go.Figure, chart_id: str) -> dcc.Graph:
    return dcc.Graph(id=chart_id, figure=figure, config={"displaylogo": False, "responsive": True})