"""
constants.py
================
All constant values, static content, and configuration for the Local
Development Tracker (LDT) Dash application.

This is a 1:1 content port of the data that lived in the Next.js version's
`src/lib/countries.ts`, `src/components/layout/site-links.ts`,
`src/app/about/page.tsx`, `src/app/methodology/page.tsx`,
`src/app/roadmap/page.tsx`, `src/app/release-notes/page.tsx`, and
`src/lib/resources.ts`.

Nothing in this module talks to a database or the filesystem - it is pure,
static, importable data and design tokens.
"""

import logging
import os

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# App-level metadata
# --------------------------------------------------------------------------

APP_TITLE = "Local Development Tracker"
APP_DESCRIPTION = (
    "Public municipality-level analytics for maps, scores, and indicator "
    "exploration."
)

# --------------------------------------------------------------------------
# Design tokens (ported from src/app/globals.css :root / .dark)
# These are consumed both by assets/styles.css (already compiled there) and
# by Python-side chart builders in utils.py, so they are duplicated here
# as the single source of truth for chart colors.
# --------------------------------------------------------------------------

COLORS_LIGHT = {
    "background": "#f7f9fd",
    "foreground": "#374291",
    "card": "#ffffff",
    "primary": "#374291",
    "secondary": "#eef2fb",
    "muted_foreground": "#3675b7",
    "accent": "#3675b7",
    "accent_strong": "#374291",
    "border_soft": "rgba(55, 66, 145, 0.10)",
    "chart_1": "#3675b7",
    "chart_2": "#e07a5f",
    "chart_3": "#2f8f6f",
    "chart_4": "#374291",
    "chart_5": "#c7923e",
    "chart_surface": "#ffffff",
    "chart_grid": "rgba(55, 66, 145, 0.09)",
    "chart_axis": "rgba(55, 66, 145, 0.34)",
    "chart_tick": "#3675b7",
    "chart_text": "#374291",
    "chart_muted_series": "#f4a261",
    "map_min": "#e5ebf8",
    "map_max": "#3675b7",
    "map_no_data": "#e7e7e7",
    "positive": "#54a24b",
    "negative": "#e45756",
    "highlight": "#f4a261",
    "highlight_line": "#9a4d00",
}

COLORS_DARK = {
    "background": "#021420",
    "foreground": "#f5f7ff",
    "card": "#071c2a",
    "primary": "#8fa8df",
    "secondary": "#0a2638",
    "muted_foreground": "#c9d3ea",
    "accent": "#8fa8df",
    "accent_strong": "#c9d3ea",
    "border_soft": "rgba(201, 211, 234, 0.14)",
    "chart_1": "#8fa8df",
    "chart_2": "#f49b78",
    "chart_3": "#62c39a",
    "chart_4": "#a8b2d1",
    "chart_5": "#d6a84f",
    "chart_surface": "rgba(7,28,42,0.96)",
    "chart_grid": "rgba(201,211,234,0.10)",
    "chart_axis": "rgba(201,211,234,0.28)",
    "chart_tick": "#c9d3ea",
    "chart_text": "#f5f7ff",
    "chart_muted_series": "rgba(201,211,234,0.54)",
    "map_min": "rgba(201,211,234,0.25)",
    "map_max": "#8fa8df",
    "map_no_data": "#193040",
    "positive": "#62c39a",
    "negative": "#ff7b72",
    "highlight": "#f4a261",
    "highlight_line": "#9a4d00",
}

GPB_CHROME_BG = "#021420"

# --------------------------------------------------------------------------
# Navigation (ported from site-links.ts)
# --------------------------------------------------------------------------

HEADER_NAV_ITEMS = [
    {"href": "?page=home", "label": "Home", "exact": True},
    {"href": "?page=about", "label": "About", "exact": False},
    {"href": "?page=methodology", "label": "Methodology", "exact": False},
    {"href": "?page=roadmap", "label": "Roadmap", "exact": False},
    {"href": "?page=resources", "label": "Resources", "exact": False},
    {"href": "?page=release-notes", "label": "Release Notes", "exact": False},
]

FOOTER_NAV_ITEMS = [
    {"href": "?page=home", "label": "Home"},
    {"href": "?page=home#country-workspaces", "label": "Country workspaces"},
    {"href": "?page=resources", "label": "Resources"},
    {"href": "?page=methodology", "label": "Methodology"},
    {"href": "?page=roadmap", "label": "Roadmap"},
    {"href": "?page=release-notes", "label": "Release Notes"},
    {"href": "?page=about", "label": "About"},
]

COUNTRY_WORKSPACE_LINKS = [
    {"href": "?page=nepal", "label": "Nepal"},
    {"href": "?page=serbia", "label": "Serbia"},
    {"href": "?page=zambia", "label": "Zambia"},
]

# --------------------------------------------------------------------------
# Countries (ported from src/lib/countries.ts)
# --------------------------------------------------------------------------

COUNTRIES = [
    {
        "code": "NPL",
        "slug": "nepal",
        "name": "Nepal",
        "analytics_status": "live",
        "fallback_data_path": "data/nepal/analytics-data.json",
        "map_data_path": "data/nepal/municipalities.geojson",
        "strategy_inventory_path": None,
        "admin_labels": {
            "lower": {"singular": "Municipality", "plural": "Municipalities"},
            "middle": {"singular": "District", "plural": "Districts"},
            "higher": {"singular": "Province", "plural": "Provinces"},
        },
        "admin_level_guide": {
            "summary": (
                "The LDT uses Nepal's province-to-local-level structure so users "
                "can compare municipalities while still reading results in their "
                "provincial planning context."
            ),
            "levels": [
                {
                    "label": "Admin level 1",
                    "name": "Province",
                    "description": (
                        "Provinces are the higher subnational frame used on the "
                        "country page to group municipalities and summarize "
                        "geographic coverage."
                    ),
                },
                {
                    "label": "Admin level 2",
                    "name": "Municipality / local level",
                    "description": (
                        "Municipalities and rural municipalities are the local "
                        "government units used for LDT analytics. Nepal's local "
                        "level includes metropolitan cities, sub-metropolitan "
                        "cities, municipalities, and rural municipalities."
                    ),
                },
            ],
            "note": (
                "As Nepal transitions into a three-tier federal administrative "
                "system, the district level, comprised of 77 distinct regions, "
                "is removed from the main LDT two-level rollup. What remains is "
                "the federal level, provincial level, and local / municipal "
                "level."
            ),
            "source_links": [
                {
                    "label": "Local government in Nepal",
                    "href": "https://en.wikipedia.org/wiki/Local_government_in_Nepal",
                },
                {
                    "label": "Administrative divisions of Nepal",
                    "href": "https://en.wikipedia.org/wiki/Administrative_divisions_of_Nepal",
                },
            ],
        },
        "profile": {
            "population_millions": None,
            "area_km2": None,
            "context": {
                "summary": (
                    "Nepal provides the baseline country workspace for the LDT, "
                    "with local analytics organized around provinces, districts, "
                    "and municipalities across a multi-year score release."
                ),
                "highlights": [
                    "The workspace is useful for comparing municipality-level "
                    "variation across terrain, population distribution, and "
                    "service access patterns.",
                    "Planning-document coverage is organized at province level "
                    "for AI-assisted local plan context.",
                    "The latest release now supports 2021-2025 time-series "
                    "exploration for the core PIL scores.",
                ],
                "source_links": [
                    {"label": "National Planning Commission", "href": "https://npc.gov.np/"},
                ],
            },
            "strategy": {
                "title": "Sixteenth Plan, 2024-2028",
                "url": "http://elibrary.moest.gov.np/bitstream/123456789/308/1/16.pdf",
            },
        },
        "planning_documents": {
            "ai_enabled": True,
            "plan_source_admin_level": "higher",
            "message": "Planning documents are available for AI-assisted analysis.",
        },
    },
    {
        "code": "ZMB",
        "slug": "zambia",
        "name": "Zambia",
        "analytics_status": "live",
        "fallback_data_path": "data/zambia/analytics-data.json",
        "map_data_path": "data/zambia/municipalities.geojson",
        "strategy_inventory_path": "data/zambia/strategy_inventory.sample.json",
        "admin_labels": {
            "lower": {"singular": "District", "plural": "Districts"},
            "middle": None,
            "higher": {"singular": "Province", "plural": "Provinces"},
        },
        "admin_level_guide": {
            "summary": (
                "The LDT uses Zambia's province-to-district structure so "
                "district-level comparisons can be understood against the "
                "country's higher administrative planning geography."
            ),
            "levels": [
                {
                    "label": "Admin level 1",
                    "name": "Province",
                    "description": (
                        "Provinces are the higher administrative grouping used "
                        "to organize district results, compare regional "
                        "patterns, and connect local evidence to national "
                        "planning priorities."
                    ),
                },
                {
                    "label": "Admin level 2",
                    "name": "District",
                    "description": (
                        "Districts are the local analysis units in the Zambia "
                        "workspace. They are the units shown in district "
                        "analytics, maps, and planning-document workflows."
                    ),
                },
            ],
            "note": (
                "The current LDT release follows the app's loaded Zambia "
                "workspace of 10 provinces and 116 districts."
            ),
            "source_links": [
                {"label": "Provinces of Zambia", "href": "https://en.wikipedia.org/wiki/Provinces_of_Zambia"},
                {"label": "Subdivisions of Zambia", "href": "https://en.wikipedia.org/wiki/Subdivisions_of_Zambia"},
            ],
        },
        "profile": {
            "population_millions": 22.5,
            "area_km2": 763027,
            "context": {
                "summary": (
                    "Zambia's LDT workspace links district-level development "
                    "conditions to a national planning agenda shaped by "
                    "economic diversification, human capital, infrastructure, "
                    "agriculture, tourism, and energy-transition minerals."
                ),
                "highlights": [
                    "The World Bank's Zambia Economic Update points to mining "
                    "momentum, an agriculture rebound, and tourism improvements "
                    "as important near-term growth signals.",
                    "The 8th National Development Plan frames implementation "
                    "around national development priorities for 2022-2026, "
                    "making district-level comparisons useful for translating "
                    "broad goals into local investment questions.",
                    "District and province labels are intentionally preserved "
                    "in the app so users can move between local plan evidence "
                    "and higher-level administrative context.",
                ],
                "source_links": [
                    {"label": "World Bank Zambia overview", "href": "https://www.worldbank.org/en/country/zambia/overview"},
                    {"label": "8th National Development Plan", "href": "https://www.cabinet.gov.zm/newsite/wp-content/uploads/2023/12/8NDP-2022-2026.pdf"},
                ],
            },
            "strategy": {
                "title": "8th National Development Plan",
                "url": "https://www.cabinet.gov.zm/newsite/wp-content/uploads/2023/12/8NDP-2022-2026.pdf",
            },
        },
        "planning_documents": {
            "ai_enabled": True,
            "plan_source_admin_level": "lower",
            "message": (
                "Local/SNG planning documents are available for AI-assisted "
                "analysis where source links are loaded."
            ),
        },
    },
    {
        "code": "SRB",
        "slug": "serbia",
        "name": "Serbia",
        "analytics_status": "live",
        "fallback_data_path": "data/serbia/analytics-data.json",
        "map_data_path": "data/serbia/municipalities.geojson",
        "strategy_inventory_path": "data/serbia/strategy_inventory.sample.json",
        "admin_labels": {
            "lower": {"singular": "Municipality", "plural": "Municipalities"},
            "middle": None,
            "higher": {"singular": "District", "plural": "Districts"},
        },
        "admin_level_guide": {
            "summary": (
                "The LDT uses Serbia's district-to-local-self-government "
                "structure so municipality-level evidence can be compared "
                "within the country's administrative district geography."
            ),
            "levels": [
                {
                    "label": "Admin level 1",
                    "name": "District",
                    "description": (
                        "Administrative districts are used in the app as the "
                        "higher grouping for Serbian municipalities and "
                        "cities, matching how the workspace summarizes local "
                        "coverage."
                    ),
                },
                {
                    "label": "Admin level 2",
                    "name": "Municipality / city",
                    "description": (
                        "Municipalities and cities are the local "
                        "self-government units used for Serbia's LDT "
                        "analytics, maps, strategy inventory, and country "
                        "landing-page counts."
                    ),
                },
            ],
            "note": (
                "Serbia's administrative districts are central-government "
                "coordination areas rather than elected local governments; "
                "the LDT uses them as a practical grouping layer for local "
                "analysis. In many Serbian contexts, Belgrade municipalities "
                "are often considered together as Belgrade, a single Admin "
                "level 1 entity, rather than as individual Admin level 2 "
                "regions."
            ),
            "source_links": [
                {
                    "label": "Statistical Office of Serbia",
                    "href": "https://www.stat.gov.rs/en-US/oblasti/registar-prostornih-jedinica-i-gis/administrativno-teritorijalna-podela-i-nstj-nivoi-1-2-3/upravni-okruzi",
                },
                {"label": "Administrative divisions of Serbia", "href": "https://en.wikipedia.org/wiki/Administrative_divisions_of_Serbia"},
            ],
        },
        "profile": {
            "population_millions": 6.7,
            "area_km2": 312717,
            "context": {
                "summary": (
                    "Serbia's LDT workspace connects municipality-level PIL "
                    "evidence to national strategy, EU-aligned reform "
                    "priorities, service delivery, competitiveness, and "
                    "climate-resilient development questions."
                ),
                "highlights": [
                    "The World Bank's Serbia partnership materials emphasize "
                    "stronger institutions, sustainable growth, and more "
                    "inclusive service delivery.",
                    "The Serbia 2030 Strategy provides the national planning "
                    "frame for reading local development patterns against "
                    "Sustainable Development Goal priorities.",
                    "Municipality and district labels are kept "
                    "country-specific so users can interpret local strategy "
                    "coverage without forcing Serbia into Nepal's "
                    "administrative terminology.",
                ],
                "source_links": [
                    {"label": "World Bank Serbia overview", "href": "https://www.worldbank.org/en/country/serbia/overview"},
                    {"label": "Serbia 2030 Strategy", "href": "https://rsjp.gov.rs/wp-content/uploads/Srbija-i-Agenda-2030.-februar-2024.-lat.pdf"},
                ],
            },
            "strategy": {
                "title": "Serbia 2030 Strategy",
                "url": "https://rsjp.gov.rs/wp-content/uploads/Srbija-i-Agenda-2030.-februar-2024.-lat.pdf",
            },
        },
        "planning_documents": {
            "ai_enabled": True,
            "plan_source_admin_level": "lower",
            "message": (
                "Local/SNG planning documents are available for AI-assisted "
                "analysis where source links are loaded."
            ),
        },
    },
]

COUNTRY_BY_SLUG = {c["slug"]: c for c in COUNTRIES}
COUNTRY_BY_CODE = {c["code"]: c for c in COUNTRIES}
DEFAULT_COUNTRY = COUNTRIES[0]

STRATEGY_INVENTORY_SLUGS = {"serbia", "zambia"}

# --------------------------------------------------------------------------
# Home page content (src/app/page.tsx)
# --------------------------------------------------------------------------

HOME_CAPABILITY_CARDS = [
    {
        "title": "Compare places",
        "body": (
            "Inspect municipalities across composite score space, peer "
            "positions, and provincial or national baselines."
        ),
    },
    {
        "title": "Read the map",
        "body": (
            "Move from pillar and indicator choropleths into municipality "
            "context, coverage, and score drivers."
        ),
    },
    {
        "title": "Trace evidence",
        "body": (
            "Keep methodology, plan sources, release notes, and data "
            "limitations close to each analytical result."
        ),
    },
    {
        "title": "Synthesize plans",
        "body": (
            "Use AI-assisted narratives, SWOT framing, and investment "
            "recommendations as inspectable planning outputs."
        ),
    },
]

# --------------------------------------------------------------------------
# About page content (src/app/about/page.tsx)
# --------------------------------------------------------------------------

ABOUT_LAYER_ONE_STEPS = [
    {
        "title": "Step 1 - Define the relevant levels of sub-national government",
        "body": (
            "Two sub-national administrative levels most relevant to the "
            "analysis are determined based on their degree of "
            "self-governance and discretionary budget control. Regions with "
            "partial to full control over budgets are better positioned to "
            "plan, invest in, and implement public projects."
        ),
    },
    {
        "title": "Step 2 - Upload the best-available boundary files",
        "body": (
            "Boundaries from official or highly reputable sources are "
            "examined for geographical accuracy, administrative "
            "consistency, and data vintage. These boundaries form the "
            "spatial unit to which indicators, scores, maps, and local "
            "analytics are linked."
        ),
    },
    {
        "title": "Step 3 - Generate PIL indicators from global big data",
        "body": (
            "Global geospatial, environmental, infrastructure, and tabular "
            "datasets are processed into comparable sub-national indicators "
            "for Prosperity, Livability, and Infrastructure. Inputs include "
            "VIIRS nighttime lights, WorldPop, GADM, OpenStreetMap, "
            "Openrouteservice, Dynamic World, ERA5, WRI Aqueduct, Climate "
            "TRACE, and other public datasets."
        ),
    },
    {
        "title": "Step 4 - Validate levels and trends for sample SNGs",
        "body": (
            "Sample municipalities or target SNGs are reviewed for "
            "plausible levels, spatial patterns, rankings, outliers, and "
            "score drivers. Results are compared with national statistics, "
            "administrative records, and local knowledge where available."
        ),
    },
    {
        "title": "Step 5 - Add national statistical and administrative data",
        "body": (
            "Global indicators provide a scalable first-pass view, but "
            "country-specific data strengthen interpretation. This may "
            "include own-source revenue, migration, employment, "
            "demographics, local strategies, national plans, project "
            "pipelines, and other planning documents."
        ),
    },
]

ABOUT_LAYER_TWO_STEPS = [
    "Build a registry of target local governments with official name, "
    "province, district, type, population, area, boundary ID, and "
    "available strategy documents.",
    "Analyze PIL scores while identifying strengths and watchpoints across "
    "Prosperity, Livability, Infrastructure, and the PIL aggregate.",
    "Identify, consolidate, and assess alignment across national, "
    "provincial, sector, donor, and local development strategies.",
    "Use GenAI and reputable web context to produce municipality-level "
    "planning narratives, development gaps, likely drivers, peer "
    "comparisons, and policy alignment.",
    "Generate evidence-backed SWOT analysis for each local government "
    "using PIL scores, strategy content, opportunities, and risks.",
    "Translate PIL evidence, strategy alignment, and SWOT outputs into "
    "public investment and asset-management recommendations.",
]

ABOUT_HIGHLIGHT_FIGURES = [
    {
        "src": "about-ldt-3d-pil-ranking.png",
        "alt": "Three-dimensional PIL ranking view for sub-national governments",
        "caption": (
            "SNGs can be ranked across three-dimensional Prosperity, "
            "Infrastructure, and Livability measures."
        ),
    },
    {
        "src": "about-ldt-2d-quadrant.png",
        "alt": "Two-dimensional quadrant analysis for prosperity and livability",
        "caption": (
            "Users can use 2D quadrant analysis for further insights, such "
            "as identifying high-prosperity and high-livability leaders."
        ),
    },
    {
        "src": "about-ldt-strategy-availability.png",
        "alt": "Strategy inventory availability view",
        "caption": "The analysis shows where SNG development strategies are available.",
    },
    {
        "src": "about-ldt-population-distribution.png",
        "alt": "Population size distribution view",
        "caption": "The tool also maps population size distribution across localities.",
    },
    {
        "src": "about-ldt-ai-swot.png",
        "alt": "AI-powered SWOT analysis panel",
        "caption": (
            "AI-powered SWOT analysis brings together insights from PIL "
            "scores and development strategy mapping."
        ),
    },
]

ABOUT_LIMITATIONS = [
    {
        "title": "Big-data proxies require validation",
        "body": (
            "Many PIL indicators are based on global geospatial datasets. "
            "These sources allow rapid, comparable analysis, but they may "
            "not perfectly reflect local conditions. Nighttime lights, "
            "accessibility layers, climate models, emissions estimates, and "
            "other proxy indicators should be checked against national "
            "statistics, administrative records, and local knowledge where "
            "available."
        ),
    },
    {
        "title": "Administrative boundaries and SNG definitions matter",
        "body": (
            "Results depend on the sub-national level selected for "
            "analysis. District-level diagnostics may hide municipal "
            "differences, while municipal-level diagnostics may be too "
            "granular for some financing instruments. The chosen geography "
            "should match the policy question and the level of government "
            "with relevant planning, budgeting, or asset-management "
            "responsibility."
        ),
    },
    {
        "title": "Local strategy documents may be missing, outdated, or uneven",
        "body": (
            "The quality of the strategy registry depends on what is "
            "publicly available and what counterparts can provide. Where "
            "local plans are unavailable, the LDT can still use PIL "
            "evidence and higher-level plans, but recommendations should be "
            "treated as first-pass planning inputs rather than substitutes "
            "for local strategy preparation."
        ),
    },
    {
        "title": "AI outputs need human review and source transparency",
        "body": (
            "AI-generated narratives, SWOTs, and investment recommendations "
            "should be inspectable. Users should be able to see which "
            "indicators, strategy documents, and source materials support "
            "each output. AI can accelerate synthesis, but sector teams, "
            "country teams, and local counterparts should review outputs "
            "before they inform policy dialogue or project pipelines."
        ),
    },
    {
        "title": "PIL scores do not capture every implementation constraint",
        "body": (
            "A low infrastructure or livability score may indicate a "
            "priority issue, but it does not establish project feasibility, "
            "fiscal affordability, readiness, procurement capacity, land "
            "availability, or operation and maintenance sustainability. The "
            "LDT should feed into public investment management processes "
            "where concepts can be screened, appraised, selected, and "
            "sequenced."
        ),
    },
]

ABOUT_COUNTRY_ROWS = [
    {
        "country": "Nepal",
        "focus": "Municipalities",
        "level_one": "7 provinces",
        "level_two": "753",
        "strategies": "0*",
        "topic": "Two municipalities from each of Madhesh, Karnali, and Sudurpashchim provinces",
    },
    {
        "country": "Serbia",
        "focus": "Municipalities",
        "level_one": "29 districts",
        "level_two": "161 Local Self Governments (LSGs)**",
        "strategies": "~94%***",
        "topic": "LIID Early Investors",
    },
    {
        "country": "Zambia",
        "focus": "Districts",
        "level_one": "10 provinces",
        "level_two": "116",
        "strategies": "~97%",
        "topic": "Mining Districts",
    },
]

ABOUT_REFERENCES = [
    "Kaiser, Kai-Alexander, Kim, Hyunseok, Mroczka, Fabienne, & Singh, "
    "Kaushiki. (2026). Public Finance Review Fundamentals: Enhancing Public "
    "Investment Development Outcomes. Washington, DC: Global Governance "
    "Practice, forthcoming.",
    "World Bank. (2025a). pim-pam.net Digital Decision Support Resources: "
    "Workplan 2026. Washington, DC: Prosperity Vertical Governance "
    "Department Public Infrastructure Investment and Asset Governance "
    "Community of Practice.",
    "World Bank. (2025b). pim-pam.net Geospatial Planning and Budgeting "
    "Platform Country Data Cube Data Catalogue. Washington, DC & Vienna, "
    "Austria: Prosperity Vertical Governance Department Public Finance and "
    "Procurement Unit.",
]

ABOUT_COUNTRY_FINDINGS = [
    {
        "title": "Nepal: filling local planning evidence gaps",
        "paragraphs": [
            "Nepal is a strong test case because the binding constraint is "
            "not the absence of local authority, but the absence of "
            "consistently available local planning evidence.",
            "Municipal development plans are not systematically available "
            "or disclosed. The LDT can use PIL diagnostics, provincial "
            "strategies, and Nepal's Sixteenth Plan as higher-level policy "
            "anchors to generate first-pass local development narratives "
            "and investment recommendations.",
        ],
    },
    {
        "title": "Serbia: moving from diagnostics to investment readiness",
        "paragraphs": [
            "Serbia demonstrates how the LDT can move beyond local "
            "diagnostics to investment-ready project matching, supporting "
            "efforts around a national ePIM system and the LIID program.",
            "The Veliko Gradiste example moves from school-access and "
            "digital-readiness evidence to recommendations on early "
            "childhood services, school infrastructure, digital equipment, "
            "and dual education linked to local labour-market needs.",
        ],
    },
    {
        "title": "Zambia: local development, mining districts, and the 9th NDP",
        "paragraphs": [
            "Zambia illustrates how the LDT can support spatial dimensions "
            "of the 9th National Development Plan and specific development "
            "challenges in mining districts.",
            "Mining districts are an important test case for linking local "
            "economic development, PIM, environmental risk, fiscal "
            "benefit-sharing, ESG risk, infrastructure, and public "
            "financial management.",
        ],
    },
]

ABOUT_FIGURE_PAIR = [
    {
        "src": "about-ldt-ai-recommendations.png",
        "alt": "AI-powered project recommendations screenshot",
        "caption": (
            "Figure 3. AI-powered project recommendations combining PIL "
            "indicators, relevant web search, and multi-level development "
            "plans."
        ),
    },
    {
        "src": "about-ldt-project-selection.png",
        "alt": "Curated existing projects in Serbia screenshot",
        "caption": (
            "Figure 4. Curated existing projects in Serbia to serve as the "
            "basis for initial project planning."
        ),
    },
]

# --------------------------------------------------------------------------
# Methodology page content (src/app/methodology/page.tsx)
# --------------------------------------------------------------------------

METHODOLOGY_INDICATOR_SELECTION = [
    "Relevance to local development outcomes that can inform public "
    "investment and planning dialogue.",
    "Availability at a subnational scale that can be harmonized across "
    "countries and administrative systems.",
    "Ability to convert raw measures into comparable 0-100 score series "
    "with transparent interpretation.",
    "Coverage across the Prosperity, Infrastructure, and Livability "
    "dimensions of the PIL framework.",
]

METHODOLOGY_PILLARS = [
    {
        "title": "Prosperity",
        "body": (
            "Prosperity captures local economic activity, productive "
            "intensity, and development opportunity. In the current "
            "country releases, it draws heavily on nighttime luminosity, "
            "built-area development, tourism activity, and "
            "agriculture-related land signals where available."
        ),
        "items": [
            "Nighttime luminosity as a proxy for economic intensity and "
            "access to electricity-enabled activity.",
            "Population- and area-normalized measures so dense urban "
            "centers and smaller local units can be compared more fairly.",
            "Country-specific economic signals, such as tourism or "
            "agricultural land indicators, where they can be processed "
            "consistently.",
        ],
    },
    {
        "title": "Infrastructure",
        "body": (
            "Infrastructure measures the availability and reach of "
            "systems that support local service delivery and "
            "connectivity. It combines digital access and service "
            "accessibility where those data are available."
        ),
        "items": [
            "Broadband and mobile internet performance.",
            "Accessibility to schools, health facilities, and key local "
            "services.",
            "Connectivity and access signals that help users compare "
            "service reach across local units.",
        ],
    },
    {
        "title": "Livability",
        "body": (
            "Livability reflects environmental, climate-risk, and "
            "human-development conditions that shape daily life. The "
            "indicator set differs by country data availability, but it "
            "is designed to make environmental stress and quality-of-life "
            "signals visible at local scale."
        ),
        "items": [
            "Air quality and emissions indicators.",
            "Road and railway exposure to flood, heat, and other "
            "climate-related hazards.",
            "Land-cover, deforestation, or green-space signals where "
            "available.",
            "Human-development conditions that complement infrastructure "
            "and prosperity scores.",
        ],
    },
]

METHODOLOGY_DATA_SOURCES = [
    {
        "title": "Satellite and environmental data",
        "items": [
            "VIIRS nighttime lights for luminosity-based economic activity "
            "measures.",
            "ERA5, OpenWeatherMaps, Climate Trace, and related climate or "
            "environmental datasets.",
            "Dynamic World and other land-cover products for built-area, "
            "vegetation, and land-use signals.",
        ],
    },
    {
        "title": "Geospatial and infrastructure data",
        "items": [
            "Administrative boundary files aligned to the relevant "
            "local-government tiers for each country.",
            "WorldPop and other gridded population sources for population "
            "aggregation and normalization.",
            "OpenStreetMap, Openrouteservice, WRI Aqueduct, and related "
            "spatial datasets for accessibility, transport, and risk "
            "measures.",
        ],
    },
    {
        "title": "Official and planning sources",
        "items": [
            "National development plans, local strategies, budgets, and "
            "other planning documents where source links are available.",
            "Official country data, partner data, and validated "
            "administrative references used to interpret local "
            "conditions.",
            "Indicator metadata that records source provenance and "
            "interpretation notes for user review.",
        ],
    },
]

METHODOLOGY_PREPROCESSING_STEPS = [
    {
        "title": "Boundary reconciliation",
        "body": (
            "Administrative names, identifiers, and geometries are "
            "harmonized so indicator tables, map boundaries, and "
            "planning-document records refer to the same local units."
        ),
    },
    {
        "title": "Spatial aggregation",
        "body": (
            "Raster, vector, network, and point datasets are aggregated "
            "to the relevant local-government level. Raster values are "
            "summarized within boundaries; point and network features are "
            "spatially joined or measured by coverage, access, or "
            "exposure."
        ),
    },
    {
        "title": "Normalization",
        "body": (
            "Indicators are normalized by population, area, or another "
            "appropriate denominator when raw totals would otherwise "
            "favor larger local units."
        ),
    },
    {
        "title": "Temporal alignment",
        "body": (
            "Input data are assigned to annual releases where possible. "
            "When countries have multi-year releases, the same local-unit "
            "keys are preserved so users can compare trends over time."
        ),
    },
]

METHODOLOGY_SCORING_STEPS = [
    "Raw indicator values are transformed into comparable score values on "
    "a 0-100 scale, where higher values represent stronger relative "
    "performance for that indicator unless explicitly documented "
    "otherwise.",
    "Component scores are grouped under Prosperity, Infrastructure, and "
    "Livability according to the PIL framework.",
    "Pillar scores use transparent equal-weight aggregation across "
    "available component scores unless a country-specific methodology "
    "states otherwise.",
    "Missing component values are not imputed inside the public app; they "
    "are skipped in aggregation where the prepared score tables identify "
    "them as missing.",
    "Published score tables are treated as the authoritative score source "
    "for maps, scatterplots, driver charts, and country landing-page "
    "summaries.",
]

METHODOLOGY_LIMITATIONS = [
    {
        "title": "Data coverage",
        "items": [
            "Not every indicator is available for every country, year, or "
            "local unit.",
            "Open geospatial sources can be incomplete or unevenly updated "
            "across territories.",
            "Planning-document coverage depends on whether source links "
            "are available and machine-readable.",
        ],
    },
    {
        "title": "Spatial interpretation",
        "items": [
            "Local-government averages can hide neighborhood-level "
            "variation.",
            "Boundary changes, naming differences, and language "
            "differences can affect matching quality.",
            "Maps and scores should be read as screening evidence, not as "
            "a substitute for project appraisal.",
        ],
    },
    {
        "title": "Scoring interpretation",
        "items": [
            "Equal weighting is transparent, but it may not reflect every "
            "sector priority or local policy preference.",
            "A high score does not automatically mean a local unit has no "
            "investment needs; it indicates relative standing within the "
            "release.",
            "Score results should be validated against local knowledge, "
            "sector diagnostics, and official planning processes.",
        ],
    },
]

# --------------------------------------------------------------------------
# Resources page content (src/lib/resources.ts)
# --------------------------------------------------------------------------

LDT_RESOURCE_FOLDER = {
    "title": "LDT reference materials",
    "href": "https://drive.google.com/drive/folders/1wUbAx7svxoAI-1de5EUHzijQSiAv5Q-a?usp=sharing",
    "description": (
        "Shared source folder for the core Local Development Tracker "
        "overview, briefing, and presentation materials."
    ),
}

LDT_RESOURCE_FILES = [
    {
        "title": "pim-pam.net GPB LDT Briefing 2026-05-23",
        "format": "Briefing",
        "href": "https://docs.google.com/document/d/1xGgjxpaJm6brzIMqib_zHJc7PKms11XR/edit?usp=drivesdk&rtpof=true&sd=true",
        "description": (
            "Long-form briefing note covering the motivation, method, "
            "early country applications, and implementation "
            "considerations for the LDT."
        ),
    },
    {
        "title": "GPBP LDT v1.4 one-pager",
        "format": "One-pager",
        "href": "https://docs.google.com/document/d/1sF1cDEyQ7nAdEB5v6MZB_40Jlpl-rLAZ/edit?usp=drivesdk&rtpof=true&sd=true",
        "description": (
            "Concise overview for quickly explaining what the LDT "
            "provides, how it supports country teams, and where it fits "
            "in the GPB suite."
        ),
    },
    {
        "title": "GPBP LDT v1.4 intro deck",
        "format": "Slide deck",
        "href": "https://docs.google.com/presentation/d/1MvANeuR3x39SgNJaD1gRFiX4DIWBpNeq/edit?usp=drivesdk&rtpof=true&sd=true",
        "description": (
            "Presentation deck for introducing the LDT workflow, country "
            "replication model, and evidence-to-planning use cases."
        ),
    },
]

COUNTRY_RESOURCE_PACKS = [
    {
        "country": "Serbia",
        "title": "Serbia country pack",
        "href": "https://drive.google.com/drive/folders/1WIOlbm9Et6-0CdmwCtw8KAIEqLdtcJbV?usp=drive_link",
        "description": (
            "Country update note and analytical notebooks for Serbia "
            "local infrastructure, inclusion, jobs, and replication work."
        ),
        "files": [
            {
                "title": "PIM-PAM SRB SNG LIID Update 2026-06-09",
                "format": "Update note",
                "href": "https://docs.google.com/document/d/134dPr5-Z4MsLMjBKVSQVGeCWvgeTQjwz/edit?usp=drivesdk&rtpof=true&sd=true",
                "description": (
                    "Serbia update note for the sub-national GPB / LIID "
                    "analysis and current country-facing findings."
                ),
            },
            {
                "title": "LIID Serbia - Visualization and Replication",
                "format": "Notebook",
                "href": "https://colab.research.google.com/drive/1G-9-BOJcl7_4XGJTbGGPhJb4Pi4KNnaQ",
                "description": (
                    "Notebook for visualizing Serbia results and "
                    "reproducing the LIID analytical workflow."
                ),
            },
            {
                "title": "LIID Serbia - Migration & Jobs Creation Analyses",
                "format": "Notebook",
                "href": "https://colab.research.google.com/drive/1G_cV3wgSVPNmknfvLNAMRw-SH5-njGNw",
                "description": (
                    "Notebook covering Serbia migration and job creation "
                    "analyses linked to local development patterns."
                ),
            },
        ],
        "empty_state": None,
    },
    {
        "country": "Zambia",
        "title": "Zambia country pack",
        "href": "https://drive.google.com/drive/folders/1bAHP-gN_0uLIIhCxhkkMBADylAvmbQdj?usp=drive_link",
        "description": (
            "Demo deck and notebooks for Zambia LDT exploration, "
            "AI-assisted analysis, and country presentation materials."
        ),
        "files": [
            {
                "title": "Pim-Pam.net GPBP Zambia Demos",
                "format": "Slide deck",
                "href": "https://docs.google.com/presentation/d/1yWxDCvVHjNd0NPjM6UMofmXHg5GEltjw1utiV5V6OEY/edit?usp=drivesdk",
                "description": (
                    "Country demo deck for sharing Zambia-specific LDT "
                    "findings and examples with stakeholders."
                ),
            },
            {
                "title": "GPBP - LDT Zambia",
                "format": "Notebook",
                "href": "https://colab.research.google.com/drive/1VOQu4l75pPo0R7kOON-3Y2aqT35XDtvC",
                "description": (
                    "Notebook for exploring Zambia LDT data preparation, "
                    "analysis, and visualization outputs."
                ),
            },
            {
                "title": "Zambia AI demo",
                "format": "Notebook",
                "href": "https://colab.research.google.com/drive/1ciSSFXsWdqI3TAvyrbg4upmUnaNWaXJD",
                "description": (
                    "Notebook demo for AI-assisted Zambia analysis and "
                    "narrative generation workflows."
                ),
            },
            {
                "title": "GPB LDT - Zambia OSR analysis",
                "format": "Notebook",
                "href": "https://drive.google.com/file/d/18DX7cuGtZcmtet1qMurQpHri_SvNQhRp/view?usp=drive_link",
                "description": (
                    "Notebook comparing Zambia PIL score patterns with "
                    "own-source revenue outcomes and mining-district "
                    "context."
                ),
            },
        ],
        "empty_state": None,
    },
    {
        "country": "Nepal",
        "title": "Nepal country pack",
        "href": "https://drive.google.com/drive/folders/115tYIXw9uxTD_MFFDQYYz66sHdqf7Inx?usp=drive_link",
        "description": (
            "Shared workspace for Nepal-specific documents, demos, "
            "analyses, and follow-up materials as they are added."
        ),
        "files": [],
        "empty_state": (
            "No top-level files were listed in the shared folder yet. "
            "Open the folder to add or review Nepal materials."
        ),
    },
]

# --------------------------------------------------------------------------
# Roadmap page content (src/app/roadmap/page.tsx)
# --------------------------------------------------------------------------

ROADMAP_NORTH_STAR_METRICS = [
    {"value": "6", "label": "Release milestones"},
    {"value": "4", "label": "Delivery workstreams"},
    {"value": "8", "label": "Release gates"},
]

ROADMAP_PHASES = [
    {
        "version": "v1.5", "name": "Trust Foundation", "horizon": "Product hardening",
        "sprint": "Sprint 1", "window": "Jul 6 - Jul 17, 2026", "deadline": "Jul 17, 2026",
        "goal": (
            "Make the current LDT reliable, consistent, and trustable, with "
            "AI brief outputs saved and replayed before heavier public "
            "investment workflows."
        ),
        "epics": [
            "Release metadata source of truth",
            "AI Brief Cache and Run Store",
            "Country Trust Card and evidence gap badges",
            "Command center polish, export MVP, responsive states",
        ],
        "gate": (
            "All public pages, exports, and AI stages use the same release "
            "metadata, caveats, source fingerprints, and cached run records."
        ),
        "accent": "#0284c7",
    },
    {
        "version": "v1.6", "name": "Evidence to Brief", "horizon": "Auditable planning outputs",
        "sprint": "Sprint 2", "window": "Jul 20 - Jul 31, 2026", "deadline": "Jul 31, 2026",
        "goal": (
            "Convert diagnostics into evidence-backed planning briefs, "
            "opportunity families, and concept-note starters."
        ),
        "epics": [
            "AI Planning Brief Report and AI Audit Drawer",
            "Investment Opportunity Finder and Evidence Graph MVP",
            "Concept Note Starter and recommendation review flow",
        ],
        "gate": (
            "Every recommendation is traceable to evidence links, caveats, "
            "and a human review status."
        ),
        "accent": "#059669",
    },
    {
        "version": "v1.7", "name": "Scaling Platform", "horizon": "Country factory and registry beta",
        "sprint": "Sprint 3", "window": "Aug 3 - Aug 14, 2026", "deadline": "Aug 14, 2026",
        "goal": (
            "Make country onboarding repeatable and introduce a "
            "lightweight public investment lifecycle view."
        ),
        "epics": [
            "Country Onboarding Factory and validation reports",
            "Document Intelligence Workbench and Trust Center",
            "PIM Registry Beta, OC4IDS-ready mapping, observability",
        ],
        "gate": (
            "A new country can be staged from manifests, data packages, "
            "source registries, and preview releases."
        ),
        "accent": "#4f46e5",
    },
    {
        "version": "v1.8", "name": "Decision Studio", "horizon": "Spatial, climate, scenario, counterpart layer",
        "sprint": "Sprint 4", "window": "Aug 17 - Aug 28, 2026", "deadline": "Aug 28, 2026",
        "goal": (
            "Add transparent spatial prioritization, climate-risk "
            "screening, scenario analysis, and workshop-ready outputs."
        ),
        "epics": [
            "Geospatial Prioritization Studio and hazard screen",
            "Scenario Builder with weights, sensitivity, and caveats",
            "Counterpart Mode and controlled API/data product",
        ],
        "gate": (
            "Scenario outputs show the weights, evidence, assumptions, "
            "map, table, caveats, and sensitivity."
        ),
        "accent": "#d97706",
    },
    {
        "version": "v1.9", "name": "Delivery Loop", "horizon": "Monitoring, transparency, and learning",
        "sprint": "Sprint 5", "window": "Aug 31 - Sep 11, 2026", "deadline": "Sep 11, 2026",
        "goal": (
            "Link upstream planning to delivery monitoring, procurement "
            "transparency, asset records, and ex-post learning."
        ),
        "epics": [
            "GEMS, KoBo, or ODK-style field evidence imports",
            "Procurement bridge, asset registry, transparency portal",
            "Cost, delay, anomaly flags and evaluation learning loops",
        ],
        "gate": (
            "Project delivery evidence can inform public transparency and "
            "future investment decisions without hiding the rule logic."
        ),
        "accent": "#e11d48",
    },
    {
        "version": "v2", "name": "MEGA Platform Migration", "horizon": "World Bank platform migration",
        "sprint": "Sprint 7", "window": "Oct 19 - Oct 31, 2026", "deadline": "Oct 31, 2026",
        "goal": (
            "Migrate the entire LDT backend and frontend to the World "
            "Bank's MEGA platform while preserving evidence lineage, "
            "country routes, exports, and auditability."
        ),
        "epics": [
            "MEGA frontend shell migration and route parity",
            "Backend service, data, auth, and deployment migration",
            "Cutover rehearsal, rollback plan, and stakeholder acceptance",
        ],
        "gate": (
            "MEGA production cutover is rehearsed, reversible, "
            "security-reviewed, and validated against existing country "
            "workflows."
        ),
        "accent": "#0891b2",
    },
]

ROADMAP_WORKSTREAMS = [
    {
        "name": "Frontend experience",
        "description": (
            "The user-facing route from command center to brief, scenario "
            "studio, and transparency surfaces."
        ),
        "steps": [
            "Trust Cards, evidence badges, AI cache provenance, command "
            "center actions",
            "Planning Brief, Audit Drawer, Opportunity Finder, review "
            "status controls",
            "Document Workbench, Trust Center, PIM Registry, admin "
            "observability",
            "Scenario Builder, Counterpart Mode, geospatial prioritization "
            "workspace",
            "MEGA-compatible frontend shell, navigation, theming, and "
            "route parity",
        ],
    },
    {
        "name": "Backend and data model",
        "description": (
            "The services, manifests, validation states, and graph links "
            "that let every visible claim be traced."
        ),
        "steps": [
            "Typed release metadata provider, AI run store, cache keys, "
            "caveat model",
            "Evidence graph nodes and edges, opportunity triggers, export "
            "lineage",
            "Country manifests, document states, registry schema, "
            "OC4IDS-ready fields",
            "Climate/geospatial layers, scenario packages, API/download "
            "contracts",
            "MEGA backend services, data migration, auth, deployment, and "
            "rollback plan",
        ],
    },
    {
        "name": "AI and evidence governance",
        "description": (
            "The policy layer that keeps AI in a synthesis role and makes "
            "source quality visible at the point of use."
        ),
        "steps": [
            "No source, no answer; persist and replay every LLM-backed "
            "brief stage",
            "Prompt versions, source fingerprints, audit records, human "
            "review status",
            "Readiness gates for translations, OCR, validation, incident "
            "handling",
            "AI summarizes tradeoffs only after deterministic outputs are "
            "shown",
            "MEGA migration preserves audit records, source fingerprints, "
            "and review states",
        ],
    },
    {
        "name": "Operating model",
        "description": (
            "The repeatable country delivery motion for analysts, data "
            "teams, counterparts, and future transparency users."
        ),
        "steps": [
            "Country trust review and release QA",
            "Analyst-reviewed opportunities and concept-note starter "
            "exports",
            "Country onboarding factory and document operations queue",
            "Workshop packs, data products, field monitoring, public "
            "learning loop",
            "MEGA cutover readiness, stakeholder signoff, support model, "
            "and training",
        ],
    },
]

ROADMAP_RELEASE_GATES = [
    "Type checks",
    "Unit tests for data providers and evidence gating",
    "Integration tests for release metadata consistency",
    "Accessibility checks for new UI surfaces",
    "Security review for AI and server routes",
    "Manual QA against at least one country workspace",
    "Export QA for Markdown, CSV, and PDF-ready outputs",
    "Source and citation QA for AI outputs",
]

ROADMAP_GUARDRAILS = [
    {
        "title": "Human authority stays explicit",
        "body": (
            "LDT can summarize, compare, draft, classify, and explain. It "
            "must not approve projects, appraise investments, commit "
            "budgets, or make procurement claims."
        ),
    },
    {
        "title": "Deterministic logic comes first",
        "body": (
            "Opportunity and scenario logic should expose triggers, "
            "weights, assumptions, caveats, and supporting evidence before "
            "AI writes a rationale."
        ),
    },
    {
        "title": "Evidence gaps are product states",
        "body": (
            "Missing plans, stale sources, blocked translations, unmatched "
            "boundaries, and sparse coverage need visible badges and "
            "exportable caveats."
        ),
    },
    {
        "title": "Every output is inspectable",
        "body": (
            "AI outputs need cache status, run ID, model, prompt version, "
            "release ID, source fingerprint, retrieval IDs, generation "
            "time, caveats, and review status."
        ),
    },
]

ROADMAP_EXECUTION_BACKLOG = [
    "Publish a first-class roadmap destination.",
    "Visualize the dated v1.5-v2 product sequence.",
    "Pull AI Brief Cache and Run Store into v1.5.",
    "Map frontend, backend, and governance workstreams.",
    "Expose release gates and AI guardrails.",
    "Add MEGA migration as the October 2026 v2 target.",
]

# --------------------------------------------------------------------------
# Release notes page content (src/app/release-notes/page.tsx)
# --------------------------------------------------------------------------

RELEASE_VERSION_TYPES = [
    {"label": "Major", "description": "Significant platform, data model, country coverage, or workflow updates."},
    {"label": "Minor", "description": "Focused UI/UX, analytics, content, or workflow improvements."},
    {"label": "Patch", "description": "Bug fixes, deployment fixes, copy corrections, and stability updates."},
    {"label": "Operational pre-release", "description": "Internal testing, preview deployments, and validation-only releases."},
]

RELEASES = [
    {
        "version": "Release v1.4.4", "date": "June 15, 2026", "type": "Minor",
        "summary": (
            "This release polishes the GPB ecosystem presentation after "
            "the multi-country release, adds a Resources page for LDT and "
            "country materials, and applies reviewer-requested content "
            "corrections across the public pages."
        ),
        "sections": [
            {"title": "GPB ecosystem UI alignment", "items": [
                "Aligned the global header and footer with the GPB digital "
                "tools guidance, including the dark chrome treatment, GPB "
                "Suite badge, PIM-PAM footer branding, and updated LDT "
                "logo usage.",
                "Reordered the primary navigation to Home, About, "
                "Methodology, Resources, and Release Notes, and replaced "
                "the previous Countries header link with About.",
                "Applied the GPB primary palette across the app while "
                "preserving the black header and footer treatment "
                "requested for the digital tools shell.",
            ]},
            {"title": "Resources page", "items": [
                "Added a Resources page to the header and footer for core "
                "LDT reference materials and country-specific workspaces.",
                "Linked the GPB LDT briefing, one-pager, and intro deck, "
                "plus Serbia, Zambia, and Nepal country folders with "
                "direct links to visible country documents, demos, and "
                "notebooks.",
                "Refined the Resources layout by removing redundant "
                "folder copy and the top-level Drive button so the page "
                "stays focused on document cards and country packs.",
            ]},
            {"title": "Content cleanup and corrections", "items": [
                "Removed the homepage implemented-by strip and the "
                "methodology standardization mapping block to reduce page "
                "clutter.",
                "Updated About page country findings to use 161 Serbia "
                "LSGs, approximately 94% Serbia strategy coverage, "
                "approximately 97% Zambia strategy coverage, and the "
                "corrected 94% Kosovo footnote.",
                "Standardized GPB Suite naming across header and footer "
                "surfaces.",
            ]},
        ],
    },
    {
        "version": "Release v1.4.3", "date": "June 13, 2026", "type": "Minor",
        "summary": (
            "This release prepares the Local Development Tracker for the "
            "next multi-country release by expanding Serbia and Zambia "
            "workspaces, strengthening the Strategy Inventory dashboard, "
            "improving country-aware AI planning support, refreshing GPB "
            "LDT branding/content, and hardening production deployment on "
            "Vercel."
        ),
        "sections": [
            {"title": "Multi-country workspaces", "items": [
                "Added live Serbia and Zambia country landing pages and "
                "analytics routes.",
                "Standardized Nepal, Serbia, and Zambia on the same shared "
                "country landing-page layout.",
                "Updated the homepage to report global workspace coverage "
                "across all loaded countries.",
                "Added generated analytics fallbacks and tracing so "
                "country analytics load correctly in production.",
            ]},
            {"title": "Strategy inventory", "items": [
                "Added Strategy Inventory dashboards for Serbia and "
                "Zambia.",
                "Added Supabase-backed strategy inventory storage and "
                "ingest support.",
                "Added fallback and sample inventory data for preview "
                "resilience.",
                "Corrected Serbia coverage and readiness logic, including "
                "the 161-LSG denominator and Serbian-language AI-readiness "
                "handling.",
            ]},
            {"title": "AI planning workflow", "items": [
                "Made AI planning requests country-aware for Nepal, "
                "Serbia, and Zambia.",
                "Updated local and SNG plan context handling while "
                "preserving existing stage compatibility.",
                "Improved graceful behavior when local plan URLs are "
                "missing.",
                "Fixed Vercel PDF parsing issues with server-side PDF.js "
                "worker and polyfill handling.",
            ]},
            {"title": "Branding, content, and documentation", "items": [
                "Refreshed the About page using the GPB LDT Briefing "
                "content.",
                "Embedded GPB LDT figures, tables, and demo screenshots "
                "from the briefing document.",
                "Updated typography to Fira Sans headings and Inter body "
                "copy.",
                "Added the PIL diagram to the homepage and Methodology "
                "page.",
                "Expanded Release Notes into a more specific versioned "
                "changelog inspired by the GPBP release-notes format.",
            ]},
            {"title": "Deployment and stability", "items": [
                "Bundled generated analytics JSON assets for Vercel.",
                "Added tracing safeguards for analytics fallbacks used by "
                "AI routes.",
                "Removed build-time Google font fetching from the "
                "Next.js build path.",
                "Added regression tests for branding/content, release "
                "notes, strategy inventory, and country-page behavior.",
            ]},
        ],
    },
    {
        "version": "Release v1.4.2", "date": "June 12, 2026", "type": "Minor",
        "summary": (
            "This release moves the app beyond the original Nepal-only "
            "framing, enables Serbia and Zambia strategy inventory "
            "workflows, and fixes production deployment issues for "
            "generated analytics assets and PDF document parsing on "
            "Vercel."
        ),
        "sections": [
            {"title": "Strategy inventory workflows", "items": [
                "Added Strategy Inventory dashboards for Serbia and "
                "Zambia.",
                "Backed the strategy inventory with a new Supabase table "
                "and ingest script.",
                "Added Serbia and Zambia sample and fallback inventory "
                "data.",
                "Corrected Serbia inventory coverage and readiness logic, "
                "including treating parsed Serbian-language documents as "
                "AI-ready.",
            ]},
            {"title": "Shared country experience", "items": [
                "Updated country landing pages so Nepal, Serbia, and "
                "Zambia use the same shared layout.",
                "Added country-aware landing actions, including the "
                "Strategy Inventory button.",
                "Made Development plan source availability collapsible by "
                "default.",
                "Updated homepage stats to summarize all loaded country "
                "workspaces instead of Nepal only.",
                "Removed static Nepal-only homepage framing.",
            ]},
            {"title": "Release notes and production fixes", "items": [
                "Added Release v1.4 notes.",
                "Fixed Vercel deployment and runtime issues for generated "
                "analytics JSON files.",
                "Added PDF.js server-side worker and polyfill handling for "
                "Vercel AI document parsing.",
            ]},
        ],
    },
    {
        "version": "Release v1.4", "date": "June 12, 2026", "type": "Major",
        "summary": (
            "This release turns the Local Development Tracker into a more "
            "complete multi-country workspace, adds Serbia and Zambia "
            "strategy inventory capabilities, and refreshes the public GPB "
            "LDT briefing content."
        ),
        "sections": [
            {"title": "Country workspaces and analytics", "items": [
                "Serbia and Zambia now have live country landing pages, "
                "analytics routes, generated analytics datasets, and "
                "country-specific boundary assets.",
                "Nepal, Serbia, and Zambia now share the same country "
                "landing-page format, including country snapshots, "
                "administrative-level summaries, SNG metrics, and "
                "plan-source availability.",
                "The homepage now reports global workspace coverage "
                "across all three loaded countries instead of presenting "
                "the application as Nepal-only.",
            ]},
            {"title": "Strategy inventory dashboard", "items": [
                "Added Serbia and Zambia Strategy Inventory pages for "
                "tracking local strategy-document availability, "
                "publication timing, AI readiness, missing plans, and "
                "follow-up needs.",
                "Backed the inventory workflow with a Supabase table, "
                "ingest script, country fallback JSON, and dashboard "
                "summaries that separate LSG-level coverage from document "
                "counts.",
                "Corrected Serbia coverage denominators to use the "
                "expected 161 LSG universe and treated parsed "
                "Serbian-language documents as AI-ready while preserving "
                "validation blockers.",
            ]},
            {"title": "AI planning and document context", "items": [
                "Made AI planning requests country-aware so Zambia and "
                "Serbia can load the correct national and local/SNG plan "
                "sources instead of defaulting to Nepal.",
                "Kept the existing province-plan AI stage name for "
                "compatibility while relabeling prompts and UI copy "
                "around local/SNG planning context.",
                "Improved graceful behavior when local plan URLs are "
                "unavailable, allowing score narratives and national-plan "
                "context to continue while blocking local-plan-dependent "
                "outputs.",
            ]},
            {"title": "Branding, content, and documentation", "items": [
                "Replaced the About page with the GPB LDT Briefing content "
                "and embedded the relevant briefing figures, country demo "
                "panels, strategy screenshots, and tables.",
                "Updated the app typography to use Fira Sans for headings "
                "and Inter for body text, with appropriate fallback "
                "fonts.",
                "Added the PIL diagram to the homepage and Methodology "
                "page to make the Prosperity, Infrastructure, and "
                "Livability framework more visible.",
            ]},
            {"title": "Deployment and stability fixes", "items": [
                "Bundled generated analytics JSON files so Serbia and "
                "Zambia analytics pages load correctly on Vercel.",
                "Added server-side PDF.js worker handling and polyfills "
                "so AI document parsing works in Vercel functions.",
                "Removed build-time Google font fetching from the "
                "Next.js build path and added tracing safeguards for "
                "generated analytics assets used by AI routes.",
            ]},
        ],
    },
    {
        "version": "Release v1.3", "date": "May 21, 2026", "type": "Minor",
        "summary": (
            "This release introduced the multi-country portal shell and "
            "prepared the app for country-specific landing pages beyond "
            "Nepal."
        ),
        "sections": [
            {"title": "Portal and navigation", "items": [
                "Reworked the homepage into a country portal with "
                "selector-based entry points for supported countries.",
                "Simplified header branding, navigation, and supporting "
                "page shells to match the multi-country product "
                "structure.",
                "Added under-construction handling for country routes "
                "that were not ready for public analytics yet.",
            ]},
            {"title": "Country pages and theming", "items": [
                "Tightened country landing-page copy and CTAs so each "
                "country page emphasizes analytics access and local "
                "context.",
                "Added persistent dark mode across the app with themed "
                "charts, improved tooltip contrast, and hydration-safe "
                "initialization.",
                "Adjusted country page positioning and shared page "
                "components so future countries can reuse the same layout "
                "patterns.",
            ]},
        ],
    },
    {
        "version": "Release v1.2", "date": "May 21, 2026", "type": "Minor",
        "summary": (
            "This release refined the AI planning brief workflow and made "
            "analytics outputs easier to inspect and interpret."
        ),
        "sections": [
            {"title": "AI workflow refinements", "items": [
                "Improved web-context output so users see clearer "
                "summaries and source lists instead of dense per-source "
                "cards.",
                "Made planning-alignment bullets denser and more directly "
                "tied to the selected score theme and planning evidence.",
                "Expanded recommendation cards with clearer "
                "implementation-risk sections and more usable structured "
                "outputs.",
            ]},
            {"title": "Score interpretation", "items": [
                "Updated Step 1 AI analysis charts to plot 0-100 component "
                "scores instead of raw indicator values.",
                "Fixed chart ranges to match score semantics so "
                "prosperity, livability, and infrastructure comparisons "
                "are easier to read.",
                "Shortened AI tab labels and helper text to reduce "
                "cognitive load during the staged analysis workflow.",
            ]},
        ],
    },
    {
        "version": "Release v1.1", "date": "May 20, 2026", "type": "Major",
        "summary": (
            "This release added the first staged AI Planning Brief "
            "workflow on top of the municipality analytics surface."
        ),
        "sections": [
            {"title": "AI Planning Brief", "items": [
                "Added staged AI routes for indicator narrative, local "
                "plan context, national plan context, web context, "
                "planning alignment, SWOT analysis, and investment "
                "recommendations.",
                "Wired document parsing and AI-stage caching into "
                "Supabase-backed server routes so repeated municipality "
                "analyses can reuse prior context.",
                "Added structured renderers for alignment, SWOT, "
                "recommendations, and web-context outputs on the "
                "analytics route.",
            ]},
            {"title": "Supporting content", "items": [
                "Aligned Release Notes, Methodology, and About pages with "
                "the expanded analytics-plus-AI product direction.",
                "Improved AI result cards so outputs are easier to scan, "
                "compare, and validate against source evidence.",
            ]},
        ],
    },
    {
        "version": "Release v1.0", "date": "May 18, 2026", "type": "Major",
        "summary": (
            "This release established the public Local Development "
            "Tracker analytics application."
        ),
        "sections": [
            {"title": "Core analytics", "items": [
                "Restored the reference-style application structure with "
                "Home, Methodology, Release Notes, and About pages.",
                "Added interactive Plotly 2D and 3D scatterplots with "
                "hover, zoom, click selection, and axis labels.",
                "Shipped the MapLibre choropleth view as the default "
                "municipality map experience.",
            ]},
            {"title": "Data foundation", "items": [
                "Completed Supabase-backed score, component, municipality "
                "context, and analytics query layers for the public app.",
                "Connected score-driver charts, indicator metadata, and "
                "municipality summaries to the runtime analytics "
                "dataset.",
            ]},
        ],
    },
]

# --------------------------------------------------------------------------
# Strategy inventory constants (src/lib/strategy-inventory/*)
# --------------------------------------------------------------------------

READINESS_CATEGORIES = [
    "AI-ready",
    "Found / Not Parsed",
    "Needs Translation",
    "Needs Validation",
    "Missing",
]

READINESS_COLORS = {
    "AI-ready": "#2f8f6f",
    "Found / Not Parsed": "#3675b7",
    "Needs Translation": "#c7923e",
    "Needs Validation": "#e07a5f",
    "Missing": "#b42318",
}

DOCUMENT_TYPES = ["strategy", "budget", "plan", "other"]
TRANSLATION_STATUSES = [
    "not_required", "translated", "needs_translation", "partial", "unknown",
]

# --------------------------------------------------------------------------
# Environment / configuration
# --------------------------------------------------------------------------

SUPABASE_URL = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
EXA_API_KEY = os.environ.get("EXA_API_KEY", "")
AI_GENERATION_ENABLED = os.environ.get("AI_GENERATION_ENABLED", "false").lower() == "true"

DEFAULT_MAP_METRIC_ID = "prosperity_score"
DEFAULT_SCATTER_X_METRIC_ID = "infrastructure_score"
DEFAULT_SCATTER_Y_METRIC_ID = "prosperity_score"

logger.info(
    "Loaded LDT constants for %s countries and %s readiness categories.",
    len(COUNTRIES),
    len(READINESS_CATEGORIES),
)
