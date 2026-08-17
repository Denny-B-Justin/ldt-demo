"""
queries.py
================
Data access layer for the Local Development Tracker.

Mirrors the query layer that lived in the Next.js app's
`src/lib/data/queries.ts`, `src/lib/country-landing-data.ts`, and
`src/lib/strategy-inventory/source.ts`.

Data source strategy (same as the original app)
-------------------------------------------------
1. **Primary source: Supabase.** If `NEXT_PUBLIC_SUPABASE_URL` and
   `SUPABASE_SERVICE_ROLE_KEY` are configured (see `.example.env`), this
   module opens a `supabase-py` client against the `analytics` schema and
   reads the same tables the Next.js app used:
       - analytics.dataset_releases
       - analytics.municipalities
       - analytics.score_definitions
       - analytics.score_components
       - analytics.indicators / analytics.indicator_sources
       - analytics.municipality_score_values
       - analytics.municipality_indicator_values
       - analytics.municipality_score_component_values
       - analytics.municipality_context_values
       - analytics.municipality_boundaries
       - analytics.strategy_inventory_documents
2. **Fallback source: bundled JSON.** If Supabase is not configured, or a
   table/query fails, the app falls back to the generated JSON snapshots
   that ship in `assets/data/<country>/analytics-data.json` and
   `assets/data/<country>/municipalities.geojson` (the same generated
   files the Next.js app bundled under `src/generated/` and
   `public/data/`). This keeps the app fully functional out of the box,
   even with no database configured, which matters for a Posit Connect
   deployment that may not have outbound DB access provisioned yet.

All heavy reads are memoized with `functools.lru_cache` (the Python
equivalent of the `react`-package `cache()` wrapper used upstream) so a
single Dash worker process only reads each JSON file once.
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

import constants

logger = logging.getLogger(__name__)

try:
    from supabase import create_client, Client  # type: ignore
except Exception:  # pragma: no cover - supabase-py is an optional dependency
    create_client = None
    Client = None

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


# --------------------------------------------------------------------------
# Supabase client
# --------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_supabase_client() -> Optional["Client"]:
    """Return a cached Supabase client, or None if not configured."""
    if create_client is None:
        logger.warning("Supabase client library is unavailable; falling back to bundled JSON data.")
        return None
    if not constants.SUPABASE_URL or not constants.SUPABASE_SERVICE_ROLE_KEY:
        logger.info("Supabase credentials are not configured; using local JSON fallback.")
        return None
    try:
        client = create_client(constants.SUPABASE_URL, constants.SUPABASE_SERVICE_ROLE_KEY)
        logger.info("Supabase connection initialized successfully.")
        return client
    except Exception:
        logger.exception("Supabase initialization failed; falling back to bundled JSON data.")
        return None


def supabase_available() -> bool:
    return get_supabase_client() is not None


# --------------------------------------------------------------------------
# Local JSON fallback loaders
# --------------------------------------------------------------------------

@lru_cache(maxsize=None)
def load_local_analytics_fallback(country_code: str) -> Dict[str, Any]:
    """Load the generated analytics-data.json fallback for a country."""
    country = constants.COUNTRY_BY_CODE.get(country_code, constants.DEFAULT_COUNTRY)
    file_path = os.path.join(ASSETS_DIR, country["fallback_data_path"])
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        logger.exception("Could not load analytics fallback for %s from %s.", country_code, file_path)
        raise


@lru_cache(maxsize=None)
def load_map_feature_collection(country_code: str) -> Dict[str, Any]:
    """Load the municipality boundary GeoJSON for a country."""
    country = constants.COUNTRY_BY_CODE.get(country_code, constants.DEFAULT_COUNTRY)
    file_path = os.path.join(ASSETS_DIR, country["map_data_path"])
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        logger.exception("Could not load map GeoJSON for %s from %s.", country_code, file_path)
        raise


@lru_cache(maxsize=None)
def load_strategy_inventory_fallback(country_code: str) -> Optional[Dict[str, Any]]:
    """Load the sample/fallback strategy inventory dataset for a country."""
    country = constants.COUNTRY_BY_CODE.get(country_code)
    if not country or not country.get("strategy_inventory_path"):
        logger.info("No strategy inventory fallback defined for country %s.", country_code)
        return None
    file_path = os.path.join(ASSETS_DIR, country["strategy_inventory_path"])
    if not os.path.exists(file_path):
        logger.warning("Strategy inventory fallback file missing for %s: %s", country_code, file_path)
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        logger.exception("Could not load strategy inventory fallback for %s from %s.", country_code, file_path)
        return None


# --------------------------------------------------------------------------
# Small numeric helpers (ports of the pure functions in queries.ts)
# --------------------------------------------------------------------------

def _finite(values):
    out = []
    for v in values:
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv == fv:  # not NaN
            out.append(fv)
    return out


def average(values) -> Optional[float]:
    finite = _finite(values)
    if not finite:
        return None
    return round(sum(finite) / len(finite), 2)


def normalize_land_area_km2(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if value > 100000:
        return round(value / 1_000_000, 2)
    return round(value, 2)


# --------------------------------------------------------------------------
# Supabase table readers (used opportunistically when configured; falls
# back silently to the local JSON snapshot on any error, matching the
# `isMissingRelationError` guard behaviour in the original queries.ts)
# --------------------------------------------------------------------------

def _try_supabase_table(table: str, builder=None, country_code: Optional[str] = None):
    client = get_supabase_client()
    if client is None:
        return None
    try:
        query = client.schema("analytics").table(table).select("*")
        if country_code is not None:
            query = query.eq("country_code", country_code)
        if builder is not None:
            query = builder(query)
        response = query.execute()
        logger.debug("Loaded %s rows from Supabase table %s for country %s.", len(response.data), table, country_code)
        return response.data
    except Exception:
        logger.exception("Supabase query failed for table %s (country=%s).", table, country_code)
        return None


# --------------------------------------------------------------------------
# Analytics page data assembly
# --------------------------------------------------------------------------

def get_analytics_dataset(country_code: str) -> Dict[str, Any]:
    """
    Return the fully-assembled analytics dataset for a country.

    This mirrors the *shape* of `AnalyticsDataset` from `types/analytics.ts`.
    The generated JSON snapshot already contains fully joined/derived
    scores, indicators, and province summaries (it was produced by the
    same pipeline that feeds Supabase upstream), so it is used directly
    as the analytical source of truth. If Supabase is configured, live
    score/indicator values for the *active* release are overlaid on top
    of the municipality roster on a best-effort basis; any failure
    silently keeps the JSON fallback values, exactly like the original
    Next.js `queries.ts` fallback strategy.
    """
    logger.debug("Loading analytics dataset for country %s.", country_code)
    dataset = load_local_analytics_fallback(country_code)

    if supabase_available():
        try:
            _overlay_supabase_scores(country_code, dataset)
        except Exception:
            logger.exception("Supabase overlay failed for analytics dataset %s; keeping bundled JSON values.", country_code)

    return dataset


def _overlay_supabase_scores(country_code: str, dataset: Dict[str, Any]) -> None:
    """Best-effort overlay of live Supabase score values onto the fallback dataset."""
    client = get_supabase_client()
    if client is None:
        return

    releases = _try_supabase_table(
        "dataset_releases",
        builder=lambda q: q.eq("country_code", country_code).order("year"),
    )
    if not releases:
        return

    active = next((r for r in releases if r.get("is_active")), releases[-1])
    release_id = active["id"]
    year = active["year"]

    score_rows = _try_supabase_table(
        "municipality_score_values",
        builder=lambda q: q.eq("release_id", release_id).eq("year", year),
    )
    if not score_rows:
        return

    scores_by_municipality: Dict[str, Dict[str, Any]] = {}
    for row in score_rows:
        scores_by_municipality.setdefault(row["municipality_id"], {})[row["score_id"]] = row["score_value"]

    municipalities = _try_supabase_table(
        "municipalities", builder=lambda q: q.eq("country_code", country_code)
    )
    if not municipalities:
        return

    by_composite_key = {m["composite_key"]: m for m in municipalities}

    for record in dataset.get("municipalities", []):
        supa_row = by_composite_key.get(record.get("compositeKey"))
        if not supa_row:
            continue
        live_scores = scores_by_municipality.get(supa_row["id"])
        if live_scores:
            record["scores"].update(live_scores)
            logger.debug("Updated live scores for %s municipality in %s.", record.get("municipality"), country_code)


def get_years(country_code: str) -> List[int]:
    return get_analytics_dataset(country_code).get("years", [])


def get_provinces(country_code: str) -> List[str]:
    provinces = get_analytics_dataset(country_code).get("provinces", [])
    return ["all"] + list(provinces)


def get_municipalities_for_year(country_code: str, year: int) -> List[Dict[str, Any]]:
    dataset = get_analytics_dataset(country_code)
    rows = [m for m in dataset["municipalities"] if m["year"] == year]
    return rows or dataset["municipalities"]


def get_municipality_options(country_code: str, year: int, province: str = "all") -> List[Dict[str, str]]:
    rows = get_municipalities_for_year(country_code, year)
    if province != "all":
        rows = [m for m in rows if m["province"] == province]
    options = [
        {"id": m["id"], "label": f"{m['municipality']}, {m['district']}"} for m in rows
    ]
    return sorted(options, key=lambda o: o["label"])


def find_municipality(country_code: str, year: int, municipality_id: str) -> Optional[Dict[str, Any]]:
    rows = get_municipalities_for_year(country_code, year)
    for m in rows:
        if m["id"] == municipality_id or m["compositeKey"] == municipality_id:
            return m
    return rows[0] if rows else None


def get_metrics(country_code: str) -> List[Dict[str, Any]]:
    return get_analytics_dataset(country_code).get("metrics", [])


def get_score_metrics(country_code: str) -> List[Dict[str, Any]]:
    return [m for m in get_metrics(country_code) if m["kind"] == "score"]


def get_score_definitions(country_code: str) -> List[Dict[str, Any]]:
    return get_analytics_dataset(country_code).get("scoreDefinitions", [])


def get_indicator_definitions(country_code: str) -> List[Dict[str, Any]]:
    return get_analytics_dataset(country_code).get("indicatorDefinitions", [])


def find_metric_by_id(metrics: List[Dict[str, Any]], metric_id: str, fallback_id: str) -> Dict[str, Any]:
    for m in metrics:
        if m["id"] == metric_id:
            return m
    for m in metrics:
        if m["id"] == fallback_id:
            return m
    return metrics[0]


def get_metric_value(municipality: Dict[str, Any], metric: Dict[str, Any]) -> Optional[float]:
    if metric["kind"] == "score":
        return municipality.get("scores", {}).get(metric["id"])
    return municipality.get("indicators", {}).get(metric["id"])


def build_metric_summary(municipalities: List[Dict[str, Any]], metric: Dict[str, Any]) -> Dict[str, Optional[float]]:
    values = _finite([get_metric_value(m, metric) for m in municipalities])
    return {
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
        "average": average(values),
    }


def build_national_component_averages(municipalities: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    component_ids = set()
    for m in municipalities:
        component_ids.update(m.get("scoreComponents", {}).keys())
    return {
        cid: average([m.get("scoreComponents", {}).get(cid) for m in municipalities])
        for cid in component_ids
    }


def build_province_summary(country_code: str, municipalities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    score_defs = get_score_definitions(country_code)
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for m in municipalities:
        grouped.setdefault(m["province"], []).append(m)

    result = []
    for province, rows in grouped.items():
        avg_scores = {
            d["id"]: average([r["scores"].get(d["id"]) for r in rows]) for d in score_defs
        }
        result.append({
            "province": province,
            "municipalityCount": len(rows),
            "averageScores": avg_scores,
        })
    return sorted(result, key=lambda r: r["province"])


def infer_score_definition(score_definitions: List[Dict[str, Any]], metric: Dict[str, Any]) -> Dict[str, Any]:
    if metric["kind"] == "score":
        for d in score_definitions:
            if d["id"] == metric["id"]:
                return d
        return score_definitions[0]
    pillar = metric.get("pillar")
    if pillar:
        for d in score_definitions:
            if d["pillar"] == pillar:
                return d
    return score_definitions[0]


def build_score_waterfalls(
    country_code: str,
    selected_municipality: Dict[str, Any],
    municipalities_for_year: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    score_definitions = get_score_definitions(country_code)
    indicator_definitions = get_indicator_definitions(country_code)
    indicator_by_id = {d["id"]: d for d in indicator_definitions}
    national_component_averages = build_national_component_averages(municipalities_for_year)

    national_score_averages = {
        d["id"]: average([m["scores"].get(d["id"]) for m in municipalities_for_year])
        for d in score_definitions
    }

    waterfalls = []
    for definition in score_definitions:
        valid_count = max(
            sum(
                1
                for cid in definition["componentIds"]
                if selected_municipality["scoreComponents"].get(cid) is not None
                and national_component_averages.get(cid) is not None
            ),
            1,
        )

        rows = []
        for index, component_id in enumerate(definition["componentIds"]):
            municipality_value = selected_municipality["scoreComponents"].get(component_id)
            national_value = national_component_averages.get(component_id)
            delta = None
            if municipality_value is not None and national_value is not None:
                delta = municipality_value - national_value
            label = (
                definition["componentLabels"][index]
                if index < len(definition["componentLabels"])
                else component_id
            )
            rows.append({
                "componentId": component_id,
                "label": label,
                "description": None,
                "municipalityValue": municipality_value,
                "nationalValue": national_value,
                "contribution": round(delta / valid_count, 2) if delta is not None else None,
            })

        municipality_score = selected_municipality["scores"].get(definition["id"])
        national_score = national_score_averages.get(definition["id"])
        total_difference = None
        if municipality_score is not None and national_score is not None:
            total_difference = round(municipality_score - national_score, 2)

        waterfalls.append({
            "scoreId": definition["id"],
            "scoreLabel": definition["label"],
            "municipalityScore": municipality_score,
            "nationalScore": national_score,
            "totalDifference": total_difference,
            "rows": rows,
        })

    return waterfalls


def get_analytics_page_data(
    country_code: str,
    year: Optional[int] = None,
    province: str = "all",
    municipality_id: Optional[str] = None,
    metric_id: Optional[str] = None,
    x_metric_id: Optional[str] = None,
    y_metric_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    The Python equivalent of `getAnalyticsPageData` in the original
    `src/lib/data/queries.ts`. Returns a single dict bundling everything
    the analytics page needs: filters, selected records, map features,
    scatter points, score-driver rows, and waterfall groups.
    """
    dataset = get_analytics_dataset(country_code)
    country = constants.COUNTRY_BY_CODE.get(country_code, constants.DEFAULT_COUNTRY)

    years = dataset["years"]
    selected_year = year if year in years else years[-1]

    municipalities_for_year = get_municipalities_for_year(country_code, selected_year)
    provinces = ["all"] + sorted({m["province"] for m in municipalities_for_year})
    selected_province = province if province in provinces else "all"

    province_filtered = (
        municipalities_for_year
        if selected_province == "all"
        else [m for m in municipalities_for_year if m["province"] == selected_province]
    )

    metrics = dataset["metrics"]
    score_metrics = [m for m in metrics if m["kind"] == "score"]

    selected_metric = find_metric_by_id(metrics, metric_id or constants.DEFAULT_MAP_METRIC_ID, constants.DEFAULT_MAP_METRIC_ID)
    selected_x_metric = find_metric_by_id(score_metrics, x_metric_id or constants.DEFAULT_SCATTER_X_METRIC_ID, constants.DEFAULT_SCATTER_X_METRIC_ID)
    selected_y_metric = find_metric_by_id(score_metrics, y_metric_id or constants.DEFAULT_SCATTER_Y_METRIC_ID, constants.DEFAULT_SCATTER_Y_METRIC_ID)

    municipality_options = [
        {"id": m["id"], "label": f"{m['municipality']}, {m['district']}"} for m in province_filtered
    ]
    municipality_options.sort(key=lambda o: o["label"])

    fallback_id = municipality_options[0]["id"] if municipality_options else (
        municipalities_for_year[0]["id"] if municipalities_for_year else None
    )
    selected_municipality = find_municipality(country_code, selected_year, municipality_id or fallback_id)
    if selected_municipality is None:
        selected_municipality = municipalities_for_year[0]

    # Map features
    feature_collection = load_map_feature_collection(country_code)
    by_composite_key = {m["compositeKey"]: m for m in municipalities_for_year}
    map_features = []
    for feature in feature_collection.get("features", []):
        composite_key = feature["properties"].get("compositeKey")
        municipality = by_composite_key.get(composite_key)
        if municipality is None:
            continue
        if selected_province != "all" and feature["properties"].get("Province") != selected_province:
            continue
        value = get_metric_value(municipality, selected_metric)
        map_features.append({
            "type": feature["type"],
            "properties": feature["properties"],
            "geometry": feature["geometry"],
            "metricValue": value,
        })

    metric_summary = build_metric_summary(province_filtered, selected_metric)

    score_definitions = get_score_definitions(country_code)
    indicator_definitions = get_indicator_definitions(country_code)
    indicator_by_id = {d["id"]: d for d in indicator_definitions}
    selected_score_definition = infer_score_definition(score_definitions, selected_metric)
    national_component_averages = build_national_component_averages(municipalities_for_year)

    score_component_definitions = []
    score_driver_rows = []
    for index, component_id in enumerate(selected_score_definition["componentIds"]):
        label = (
            selected_score_definition["componentLabels"][index]
            if index < len(selected_score_definition["componentLabels"])
            else component_id
        )
        score_component_definitions.append({"id": component_id, "label": label, "description": None})
        municipality_value = selected_municipality["scoreComponents"].get(component_id)
        national_value = national_component_averages.get(component_id)
        delta = None
        if municipality_value is not None and national_value is not None:
            delta = round(municipality_value - national_value, 2)
        score_driver_rows.append({
            "componentId": component_id,
            "label": label,
            "municipalityValue": municipality_value,
            "nationalValue": national_value,
            "delta": delta,
        })

    waterfalls = build_score_waterfalls(country_code, selected_municipality, municipalities_for_year)
    province_summary = build_province_summary(country_code, municipalities_for_year)

    scatter2d_points = []
    for m in province_filtered:
        scatter2d_points.append({
            "id": m["id"],
            "label": m["municipality"],
            "district": m["district"],
            "province": m["province"],
            "x": m["scores"].get(selected_x_metric["id"]),
            "y": m["scores"].get(selected_y_metric["id"]),
            "selected": m["id"] == selected_municipality["id"],
        })

    scatter3d_points = []
    for m in province_filtered:
        scatter3d_points.append({
            "id": m["id"],
            "label": m["municipality"],
            "district": m["district"],
            "province": m["province"],
            "x": m["scores"].get("prosperity_score"),
            "y": m["scores"].get("infrastructure_score"),
            "z": m["scores"].get("livability_score"),
            "selected": m["id"] == selected_municipality["id"],
        })

    coverage = dataset.get("coverage", {})

    return {
        "country": {"code": country["code"], "slug": country["slug"], "name": country["name"]},
        "release": dataset.get("release", {}),
        "filters": {
            "years": years,
            "provinces": provinces,
            "metrics": metrics,
            "scoreMetrics": score_metrics,
            "municipalities": municipality_options,
        },
        "coverage": coverage,
        "selected": {
            "year": selected_year,
            "province": selected_province,
            "municipalityId": selected_municipality["id"],
            "municipalityName": selected_municipality["municipality"],
            "metricId": selected_metric["id"],
            "xMetricId": selected_x_metric["id"],
            "yMetricId": selected_y_metric["id"],
        },
        "municipality": selected_municipality,
        "map": {
            "metric": selected_metric,
            "features": map_features,
            "summary": metric_summary,
            "coverageLabel": f"{coverage.get('mapMunicipalityCount', 0)} mapped of {len(municipalities_for_year)} analytics municipalities",
        },
        "scatter2d": {"xMetric": selected_x_metric, "yMetric": selected_y_metric, "points": scatter2d_points},
        "scatter3d": {"points": scatter3d_points},
        "metadata": {
            "selectedMetric": indicator_by_id.get(selected_metric["id"]),
            "scoreDefinition": selected_score_definition,
            "scoreComponents": score_component_definitions,
            "scoreDriverRows": score_driver_rows,
        },
        "waterfalls": waterfalls,
        "provinceSummary": province_summary,
    }


def get_methodology_data(country_code: str = None) -> Dict[str, Any]:
    country_code = country_code or constants.DEFAULT_COUNTRY["code"]
    dataset = get_analytics_dataset(country_code)
    return {
        "indicatorDefinitions": dataset.get("indicatorDefinitions", []),
        "scoreDefinitions": dataset.get("scoreDefinitions", []),
        "metrics": dataset.get("metrics", []),
        "coverage": dataset.get("coverage", {}),
    }


# --------------------------------------------------------------------------
# Country landing-page dataset
# --------------------------------------------------------------------------

def load_country_dataset(country_code: str) -> Dict[str, Any]:
    """Equivalent of `loadCountryDataset` from country-landing-data.ts."""
    return get_analytics_dataset(country_code)


def sum_finite(values) -> float:
    return sum(_finite(values))


def build_country_home_model(country: Dict[str, Any], dataset: Dict[str, Any]) -> Dict[str, Any]:
    """Port of `buildCountryHomeModel` from country-home.ts."""
    release_year = dataset.get("release", {}).get("year", 0)
    years = dataset.get("years", [release_year])
    latest_year = max([release_year] + list(years))

    rows = [m for m in dataset["municipalities"] if m["year"] == latest_year]
    if not rows:
        rows = dataset["municipalities"]

    total_population = sum_finite([m["context"].get("population") for m in rows])
    total_area = sum_finite([m["context"].get("totalLandAreaKm2") for m in rows])

    population_millions = country["profile"]["population_millions"]
    if population_millions is None:
        population_millions = total_population / 1_000_000
    area_km2 = country["profile"]["area_km2"]
    if area_km2 is None:
        area_km2 = total_area

    grouped: Dict[str, List[str]] = {}
    for m in rows:
        grouped.setdefault(m["province"], []).append(m["municipality"])

    groups = [
        {"name": name, "lowerUnits": sorted(units)}
        for name, units in grouped.items()
    ]
    groups.sort(key=lambda g: g["name"])

    return {
        "latestYear": latest_year,
        "releaseKey": dataset.get("release", {}).get("key", ""),
        "lowerCount": len(rows),
        "higherCount": len(groups),
        "populationLabel": f"{population_millions:.1f} million",
        "areaLabel": f"{area_km2:,.1f} sq km",
        "groups": groups,
    }


def get_country_landing_actions(country: Dict[str, Any]) -> List[Dict[str, str]]:
    lower_unit_label = country["admin_labels"]["lower"]["singular"]
    lower_unit_label = lower_unit_label[0].lower() + lower_unit_label[1:]

    actions = [
        {
            "label": f"Analyze {lower_unit_label} metrics",
            "href": f"?page={country['slug']}&view=analytics",
            "variant": "primary",
            "align": "left",
        }
    ]

    if country["slug"] in constants.STRATEGY_INVENTORY_SLUGS:
        actions.append({
            "label": "Strategy inventory",
            "href": f"?page={country['slug']}&view=strategy-inventory",
            "variant": "secondary",
            "align": "left",
        })

    actions.append({
        "label": "Return to Homepage",
        "href": "?page=home",
        "variant": "secondary",
        "align": "right",
    })

    return actions


def get_plan_availability_disclosure(country: Dict[str, Any]) -> Dict[str, str]:
    plan_level = country["planning_documents"]["plan_source_admin_level"]
    if plan_level == "lower":
        label = country["admin_labels"]["lower"]["plural"]
    else:
        label = country["admin_labels"]["higher"]["plural"]
    tracked_unit_label = label[0].lower() + label[1:]

    return {
        "trackedUnitLabel": tracked_unit_label,
        "description": (
            f"{country['planning_documents']['message']} This section tracks "
            f"which {tracked_unit_label} currently have local/SNG plan links "
            f"available for AI-assisted analysis."
        ),
    }


# --------------------------------------------------------------------------
# Strategy inventory
# --------------------------------------------------------------------------

def get_strategy_inventory_dataset(country_code: str) -> Optional[Dict[str, Any]]:
    """
    Load the strategy inventory dataset for a country. Tries Supabase's
    `analytics.strategy_inventory_documents` table first; falls back to
    the bundled sample JSON (matching `strategy-inventory/source.ts`).
    """
    country = constants.COUNTRY_BY_CODE.get(country_code)
    if not country or country["slug"] not in constants.STRATEGY_INVENTORY_SLUGS:
        return None

    supabase_rows = _try_supabase_table(
        "strategy_inventory_documents",
        builder=lambda q: q.eq("is_active", True),
        country_code=country_code,
    )

    if supabase_rows:
        return {
            "country_code": country_code,
            "country_name": country["name"],
            "is_sample_data": False,
            "expected_lsg_count": len(supabase_rows),
            "last_updated": max((r.get("last_updated") or "" for r in supabase_rows), default=""),
            "summary_override": None,
            "records": supabase_rows,
        }

    return load_strategy_inventory_fallback(country_code)


def get_readiness_category(record: Dict[str, Any]) -> str:
    """Port of `getReadinessCategory` from strategy-inventory/summarize.ts."""
    source_status = record.get("source_status")
    if source_status in ("missing", "not_available"):
        return "Missing"

    parsing_status = record.get("parsing_status")
    if source_status == "needs_validation" or parsing_status in ("failed", "needs_review"):
        return "Needs Validation"

    is_serbian_exception = record.get("country_code") == "SRB" and record.get("language") == "sr"
    is_ai_ready = (
        source_status == "found"
        and parsing_status == "parsed"
        and (record.get("ai_ready") or is_serbian_exception)
    )
    if is_ai_ready:
        return "AI-ready"

    translation_status = record.get("translation_status")
    needs_translation = not is_serbian_exception and translation_status in ("needs_translation", "partial")
    if needs_translation:
        return "Needs Translation"

    return "Found / Not Parsed"


def get_strategy_inventory_summary(
    records: List[Dict[str, Any]], expected_lsgs: int, summary_override: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Port of `getStrategyInventoryDisplaySummary`."""

    def has_document_source(record):
        return record.get("source_status") in ("found", "needs_validation")

    def lsg_key(record):
        return (record.get("lsg_id") or record.get("lsg_name") or "").strip().lower()

    document_records = [r for r in records if has_document_source(r)]
    covered_keys = {lsg_key(r) for r in document_records}

    missing_records = [r for r in records if not has_document_source(r)]
    seen = set()
    missing_lsgs = []
    for r in missing_records:
        key = lsg_key(r)
        if key in seen:
            continue
        seen.add(key)
        missing_lsgs.append({"lsg_id": r.get("lsg_id"), "lsg_name": r.get("lsg_name"), "region_name": r.get("region_name")})

    publication_year_counts: Dict[str, int] = {}
    for r in document_records:
        year = str(r["publication_year"]) if r.get("publication_year") else "Unknown"
        publication_year_counts[year] = publication_year_counts.get(year, 0) + 1

    status_counts = {c: 0 for c in constants.READINESS_CATEGORIES}
    for r in records:
        category = get_readiness_category(r)
        status_counts[category] = status_counts.get(category, 0) + 1

    total_missing = max(status_counts.get("Missing", 0), len(missing_lsgs))
    status_counts["Missing"] = total_missing

    summary = {
        "expected_lsgs": expected_lsgs,
        "lsgs_with_any_document": len(covered_keys),
        "coverage_rate": (len(covered_keys) / expected_lsgs) if expected_lsgs else 0,
        "total_documents_found": len(document_records),
        "strategies_found": len([r for r in document_records if r.get("document_type") == "strategy"]),
        "budgets_found": len([r for r in document_records if r.get("document_type") == "budget"]),
        "ai_ready_documents": len([r for r in records if get_readiness_category(r) == "AI-ready"]),
        "needs_translation": len([r for r in records if get_readiness_category(r) == "Needs Translation"]),
        "needs_validation": len([r for r in records if get_readiness_category(r) == "Needs Validation"]),
        "missing_lsgs": missing_lsgs,
        "publication_year_counts": sorted(
            [{"year": y, "count": c} for y, c in publication_year_counts.items()],
            key=lambda row: (row["year"] == "Unknown", row["year"]),
        ),
        "status_breakdown": [{"category": c, "count": status_counts[c]} for c in constants.READINESS_CATEGORIES],
        "latest_last_updated": max((r.get("last_updated") or "" for r in records), default=None) or None,
    }

    if summary_override:
        summary.update({k: v for k, v in summary_override.items() if v is not None})

    return summary