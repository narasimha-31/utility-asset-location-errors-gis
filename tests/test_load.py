import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point, Polygon

import load


def test_to_feet_gives_us_feet():
    pts = gpd.GeoDataFrame(geometry=[Point(-95.4, 29.700), Point(-95.4, 29.701)], crs=4326)
    feet = load.to_feet(pts)
    assert feet.crs.to_epsg() == 2278
    # 0.001 degree of latitude near Houston is about 364 ft
    assert feet.geometry.iloc[0].distance(feet.geometry.iloc[1]) == pytest.approx(364, abs=2)


def osm_sample():
    return gpd.GeoDataFrame(
        {"osm_id": [1, 2, 3, 4, 5],
         "osm_type": ["node", "node", "way", "way", "way"],
         "power": ["pole", "tower", "line", "minor_line", "substation"],
         "voltage": [None, None, "138000", None, None],
         "operator": [None, None, "Example Utility", None, None]},
        geometry=[Point(-95.40, 29.70), Point(-95.41, 29.70),
                  LineString([(-95.40, 29.70), (-95.41, 29.70)]),
                  LineString([(-95.40, 29.71), (-95.41, 29.71)]),
                  Polygon([(-95.42, 29.70), (-95.42, 29.71), (-95.43, 29.71), (-95.42, 29.70)])],
        crs=4326,
    )


def test_split_osm_puts_each_type_in_its_table():
    parts = load.split_osm(osm_sample())
    assert list(parts["osm_supports"]["power"]) == ["pole", "tower"]
    assert list(parts["osm_lines"]["power"]) == ["line", "minor_line"]
    assert list(parts["osm_substations"]["osm_id"]) == [5]
    assert {"voltage", "operator"} <= set(parts["osm_lines"].columns)


def test_hifld_lines_copied_from_osm_are_marked():
    raw = gpd.GeoDataFrame(
        {"ID": ["1", "2"], "OWNER": ["A", "B"], "VOLTAGE": [138, 69],
         "SOURCE": ["IMAGERY", "IMAGERY, OpenStreetMap"]},
        geometry=[LineString([(-95.4, 29.7), (-95.41, 29.7)])] * 2,
        crs=4326,
    )
    hifld = load.prep_hifld(raw)
    assert list(hifld["from_osm"]) == [False, True]
    assert {"id", "owner", "voltage", "source"} <= set(hifld.columns)


def test_clip_cuts_lines_at_the_study_area_edge():
    line = gpd.GeoDataFrame(geometry=[LineString([(-95.40, 29.70), (-94.40, 29.70)])], crs=4326)
    clipped = load.clip_to_study_area(line)
    assert clipped.geometry.iloc[0].bounds[2] == pytest.approx(-95.25)


def test_load_all_writes_tables_in_feet(tmp_path, test_engine):
    osm_sample().to_file(tmp_path / "osm_power.geojson", driver="GeoJSON")
    gpd.GeoDataFrame(
        {"ID": ["1"], "OWNER": ["A"], "VOLTAGE": [138], "SOURCE": ["IMAGERY"]},
        geometry=[LineString([(-95.4, 29.7), (-95.41, 29.7)])], crs=4326,
    ).to_file(tmp_path / "hifld_lines.geojson", driver="GeoJSON")
    gpd.GeoDataFrame(
        {"FLD_ZONE": ["AE"], "ZONE_SUBTY": [None], "SFHA_TF": ["T"]},
        geometry=[Polygon([(-95.5, 29.6), (-95.5, 29.8), (-95.3, 29.8), (-95.5, 29.6)])], crs=4326,
    ).to_file(tmp_path / "flood_zones.geojson", driver="GeoJSON")

    counts = load.load_all(test_engine, raw_dir=tmp_path)
    assert counts == {"osm_supports": 2, "osm_lines": 2, "osm_substations": 1,
                      "hifld_lines": 1, "flood_zones": 1, "study_area": 1}

    with test_engine.connect() as conn:
        srid = conn.exec_driver_sql("SELECT Find_SRID('public', 'osm_lines', 'geom')").scalar()
    assert srid == 2278
