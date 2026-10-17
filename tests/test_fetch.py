import geopandas as gpd
import pytest
from shapely.geometry import LineString

import fetch


def test_node_becomes_point():
    gdf = fetch.overpass_to_gdf([
        {"type": "node", "id": 1, "lat": 29.7, "lon": -95.4, "tags": {"power": "pole"}},
    ])
    assert gdf.geometry.iloc[0].geom_type == "Point"
    assert (gdf.geometry.iloc[0].x, gdf.geometry.iloc[0].y) == (-95.4, 29.7)
    assert gdf.crs.to_epsg() == 4326


def test_way_becomes_linestring_with_same_vertices():
    gdf = fetch.overpass_to_gdf([
        {"type": "way", "id": 2, "tags": {"power": "line"},
         "geometry": [{"lat": 29.70, "lon": -95.40}, {"lat": 29.71, "lon": -95.41},
                      {"lat": 29.72, "lon": -95.42}]},
    ])
    assert gdf.geometry.iloc[0].geom_type == "LineString"
    assert len(gdf.geometry.iloc[0].coords) == 3


def test_closed_substation_way_becomes_polygon():
    ring = [{"lat": 29.70, "lon": -95.40}, {"lat": 29.70, "lon": -95.39},
            {"lat": 29.71, "lon": -95.39}, {"lat": 29.70, "lon": -95.40}]
    gdf = fetch.overpass_to_gdf([
        {"type": "way", "id": 3, "tags": {"power": "substation"}, "geometry": ring},
    ])
    assert gdf.geometry.iloc[0].geom_type == "Polygon"


def test_tags_and_ids_become_columns():
    gdf = fetch.overpass_to_gdf([
        {"type": "node", "id": 7, "lat": 29.7, "lon": -95.4,
         "tags": {"power": "tower", "operator": "Example Utility"}},
    ])
    row = gdf.iloc[0]
    assert row["osm_id"] == 7
    assert row["osm_type"] == "node"
    assert row["power"] == "tower"
    assert row["operator"] == "Example Utility"


def page(n, start=0):
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"ID": str(start + i)},
         "geometry": {"type": "Point", "coordinates": [-95.4, 29.7]}}
        for i in range(n)
    ]}


def test_fetch_arcgis_reads_every_page():
    pages = [page(2000, 0), page(2000, 2000), page(5, 4000)]
    offsets = []

    def fake_get(url, params):
        offsets.append(params["resultOffset"])
        return pages[len(offsets) - 1]

    gdf = fetch.fetch_arcgis("http://example", fetch.BBOX, get=fake_get)
    assert len(gdf) == 4005
    assert offsets == [0, 2000, 4000]


def test_hifld_uses_archive_when_service_fails(tmp_path):
    archive = gpd.GeoDataFrame(
        {"ID": ["a", "b"], "SOURCE": ["IMAGERY", "IMAGERY"]},
        geometry=[LineString([(-95.40, 29.70), (-95.39, 29.71)]),
                  LineString([(-90.00, 35.00), (-90.01, 35.01)])],
        crs=4326,
    )
    archive.to_file(tmp_path / "Electric_Power_Transmission_Lines.gpkg")

    def broken_get(url, params):
        raise ConnectionError("service down")

    gdf = fetch.load_hifld(get=broken_get, archive_dir=tmp_path)
    # second line is outside the study area
    assert list(gdf["ID"]) == ["a"]


def test_hifld_stops_with_link_when_no_archive(tmp_path):
    def broken_get(url, params):
        raise ConnectionError("service down")

    with pytest.raises(SystemExit, match="datalumos"):
        fetch.load_hifld(get=broken_get, archive_dir=tmp_path)
