"""Geometry decode (WKT / WKB-hex / GeoJSON) + simplify + multi-row merge."""

from __future__ import annotations

import json

from shapely.geometry import Polygon

import queries

_WKT = "POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))"


def test_decode_wkt():
    geom = queries._decode_geometry(_WKT)
    assert geom.geom_type == "Polygon"
    assert geom.equals(Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]))


def test_decode_wkb_hex():
    wkb_hex = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]).wkb_hex
    geom = queries._decode_geometry(wkb_hex)
    assert geom.geom_type == "Polygon"


def test_decode_wkb_bytes():
    wkb_bytes = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]).wkb
    geom = queries._decode_geometry(wkb_bytes)
    assert geom.geom_type == "Polygon"


def test_decode_geojson_string():
    gj = json.dumps({"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]})
    geom = queries._decode_geometry(gj)
    assert geom.geom_type == "Polygon"


def test_decode_none_and_blank():
    assert queries._decode_geometry(None) is None
    assert queries._decode_geometry("") is None


def test_geometry_to_geojson_simplifies():
    # a many-vertex near-square ring
    coords = [(i / 100, 0) for i in range(101)] + [(1, 1), (0, 1), (0, 0)]
    geom = Polygon(coords)
    gj = queries._geometry_to_geojson(geom, tolerance=0.1)
    assert gj["type"] == "Polygon"
    assert len(gj["coordinates"][0]) < len(coords)


def test_feature_collection_merges_multi_row(zmb_dataset):
    fc = queries.load_map_feature_collection("ZMB")
    by_key = {f["properties"]["compositeKey"]: f for f in fc["features"]}
    lusaka = by_key["Lusaka::Lusaka::Lusaka"]
    # two input polygons merged into one geometry
    assert lusaka["geometry"]["type"] in ("Polygon", "MultiPolygon")
    assert lusaka["properties"]["Municipality"] == "Lusaka"


def test_feature_collection_includes_unmatched_boundary(zmb_dataset):
    fc = queries.load_map_feature_collection("ZMB")
    keys = {f["properties"]["compositeKey"] for f in fc["features"]}
    assert "Copperbelt::Copperbelt::Ndola" in keys  # present, just not analytics-matched
