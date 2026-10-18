"""Recount every check from the raw files and compare with the database."""
import re

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import MultiLineString
from shapely.ops import unary_union

import load
from db import get_engine

# same tolerances as checks.sql, in US feet
LOCATION_FT = 100
STEP_FT = 5
SUPPORT_FT = 5
TOUCH_FT = 1
SUBSTATION_FT = 50
VOLTAGE_PATTERN = re.compile(r"^[0-9]+(;[0-9]+)*$")


def empty(series):
    return series.isna() | (series.astype(str).str.strip() == "")


def ids(gdf):
    return set(gdf["osm_id"].astype(str))


def sample_points(geom, step):
    lines = geom.geoms if isinstance(geom, MultiLineString) else [geom]
    points = []
    for line in lines:
        for d in np.append(np.arange(0, line.length, step), line.length):
            points.append(line.interpolate(d))
    return points


def worst_gap(geom, lines_gdf):
    pts = gpd.GeoDataFrame(geometry=sample_points(geom, STEP_FT), crs=lines_gdf.crs)
    return gpd.sjoin_nearest(pts, lines_gdf[["geometry"]], distance_col="d")["d"].max()


def recompute():
    raw = load.RAW
    osm = load.to_feet(gpd.read_file(raw / "osm_power.geojson"))
    supports = osm[osm["power"].isin(["pole", "tower"])]
    lines = osm[osm["power"].isin(["line", "minor_line"])].reset_index(drop=True)
    subs = osm[osm["power"] == "substation"]
    transmission = lines[lines["power"] == "line"]
    hifld = load.to_feet(load.clip_to_study_area(
        load.prep_hifld(gpd.read_file(raw / "hifld_lines.geojson"))))
    independent = hifld[~hifld["from_osm"]]
    area = load.to_feet(load.study_area()).geometry.iloc[0]
    found = {}

    found["osm_hifld_disagreement"] = {
        str(row["id"]) for _, row in independent.iterrows()
        if worst_gap(row.geometry, transmission) > LOCATION_FT
    }

    d = gpd.sjoin_nearest(supports[["geometry"]], lines[["geometry"]], distance_col="d")\
        .groupby(level=0)["d"].min()
    found["support_not_on_line"] = ids(supports.loc[d[d > SUPPORT_FT].index])

    # line groups
    blobs = unary_union(lines.geometry.buffer(TOUCH_FT / 2))
    blobs = list(getattr(blobs, "geoms", [blobs]))
    blob_gdf = gpd.GeoDataFrame({"grp": range(len(blobs))}, geometry=blobs, crs=lines.crs)
    group = gpd.sjoin(lines[["geometry"]], blob_gdf, predicate="intersects")["grp"]\
        .groupby(level=0).first()
    near_sub = lines.geometry.apply(lambda g: subs.distance(g).min() <= SUBSTATION_FT)
    leaves = ~lines.geometry.within(area)
    group_ok = (near_sub | leaves).groupby(group).any()
    found["possible_mapping_gap"] = ids(lines[~group.map(group_ok)])

    found["missing_voltage"] = ids(lines[empty(lines["voltage"])])
    found["missing_operator"] = ids(lines[empty(lines["operator"])])
    bad = ~empty(lines["voltage"]) & ~lines["voltage"].astype(str).str.match(VOLTAGE_PATTERN)
    found["bad_voltage"] = ids(lines[bad])
    named = lines.loc[~empty(lines["operator"]), "operator"]
    keys = named.str.replace(r"[^A-Za-z0-9]", "", regex=True).str.lower()
    spellings = named.groupby(keys).nunique()
    found["inconsistent_operator"] = ids(lines.loc[keys[keys.isin(spellings[spellings > 1].index)].index])

    good = transmission[transmission["voltage"].astype(str).str.match(VOLTAGE_PATTERN)]
    mids = gpd.GeoDataFrame(good[["osm_id", "voltage"]],
                            geometry=good.geometry.interpolate(0.5, normalized=True), crs=lines.crs)
    ref = independent[independent["voltage"] > 0][["voltage", "geometry"]]\
        .rename(columns={"voltage": "kv"})
    pairs = gpd.sjoin_nearest(mids, ref, max_distance=LOCATION_FT, distance_col="d")
    pairs = pairs[~pairs.index.duplicated()]
    differs = pairs.apply(
        lambda r: r["kv"] * 1000 not in [float(v) for v in r["voltage"].split(";")], axis=1)
    found["voltage_disagreement"] = ids(pairs[differs])
    return found


def database_ids(engine):
    df = pd.read_sql("SELECT check_name, feature_id FROM ranked_errors", engine)
    return df.groupby("check_name")["feature_id"].apply(set).to_dict()


def main():
    independent = recompute()
    db = database_ids(get_engine())
    print(f"{'check':26} {'database':>9} {'recomputed':>11}  same features")
    all_match = True
    for check, theirs in independent.items():
        ours = db.get(check, set())
        same = ours == theirs
        all_match &= same
        print(f"{check:26} {len(ours):>9} {len(theirs):>11}  {'yes' if same else 'NO'}")
    if all_match:
        print("\nevery check flags exactly the same features")
    else:
        print("\nsome checks differ, look into them")


if __name__ == "__main__":
    main()
