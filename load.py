from pathlib import Path

import geopandas as gpd
from geoalchemy2 import Geometry
from shapely.geometry import box
from sqlalchemy import text

from db import get_engine
from fetch import BBOX

RAW = Path("data/raw")
# NAD83 Texas South Central, US feet
FEET = 2278


def to_feet(gdf):
    return gdf.to_crs(FEET)


def study_area():
    s, w, n, e = BBOX
    return gpd.GeoDataFrame(geometry=[box(w, s, e, n)], crs=4326)


def clip_to_study_area(gdf):
    return gdf.clip(study_area().geometry.iloc[0])


def _keep(gdf, columns):
    gdf = gdf.copy()
    # tag may not exist in this extract
    for col in columns:
        if col not in gdf.columns:
            gdf[col] = None
    return gdf[columns + ["geometry"]]


def split_osm(osm):
    supports = osm[osm["power"].isin(["pole", "tower"])]
    lines = osm[osm["power"].isin(["line", "minor_line"])]
    subs = osm[osm["power"] == "substation"]
    return {
        "osm_supports": _keep(supports, ["osm_id", "power", "operator"]),
        "osm_lines": _keep(lines, ["osm_id", "power", "voltage", "operator"]),
        "osm_substations": _keep(subs, ["osm_id", "name", "operator"]),
    }


def prep_hifld(raw):
    hifld = raw.rename(columns={"ID": "id", "OWNER": "owner",
                                "VOLTAGE": "voltage", "SOURCE": "source"})
    hifld = hifld[["id", "owner", "voltage", "source", "geometry"]].copy()
    # copied from osm
    hifld["from_osm"] = hifld["source"].fillna("").str.contains("openstreetmap", case=False)
    return hifld


def prep_flood(raw):
    flood = raw.rename(columns={"FLD_ZONE": "fld_zone", "ZONE_SUBTY": "zone_subty",
                                "SFHA_TF": "sfha_tf"})
    return flood[["fld_zone", "zone_subty", "sfha_tf", "geometry"]].copy()


def write(gdf, table, engine):
    gdf = to_feet(gdf).rename_geometry("geom")
    gdf.to_postgis(table, engine, if_exists="replace", index=False,
                   dtype={"geom": Geometry("GEOMETRY", srid=FEET)})
    with engine.begin() as conn:
        conn.execute(text(
            f"CREATE INDEX IF NOT EXISTS {table}_geom_idx ON {table} USING gist (geom)"
        ))
    return len(gdf)


def load_all(engine, raw_dir=RAW):
    raw_dir = Path(raw_dir)
    tables = split_osm(gpd.read_file(raw_dir / "osm_power.geojson"))
    # hifld lines run past the box
    hifld = prep_hifld(gpd.read_file(raw_dir / "hifld_lines.geojson"))
    tables["hifld_lines"] = clip_to_study_area(hifld)
    tables["flood_zones"] = prep_flood(gpd.read_file(raw_dir / "flood_zones.geojson"))
    tables["study_area"] = study_area()
    return {name: write(gdf, name, engine) for name, gdf in tables.items()}


if __name__ == "__main__":
    for table, count in load_all(get_engine()).items():
        print(f"{table}: {count}")
