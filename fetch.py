import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import linemerge, polygonize, unary_union

# south, west, north, east
BBOX = (29.65, -95.50, 29.85, -95.25)
RAW = Path("data/raw")

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
HIFLD_URL = ("https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/"
             "US_Electric_Power_Transmission_Lines/FeatureServer/0")
FEMA_URL = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28"
HIFLD_ARCHIVE_LINK = "https://www.datalumos.org/datalumos/project/240591/version/V1/view"
PAGE_SIZE = 2000


def get_json(url, params, tries=3, wait=30):
    for attempt in range(1, tries + 1):
        try:
            r = requests.post(url, data=params, timeout=180,
                              headers={"User-Agent": "houston-gis-qa/0.1"})
            if r.status_code in (429, 502, 503, 504):
                raise requests.HTTPError(f"{r.status_code} from {url}")
            r.raise_for_status()
            data = r.json()
            if "error" in data:
                raise requests.HTTPError(f"{url} returned {data['error']}")
            return data
        except (requests.RequestException, ValueError) as e:
            if attempt == tries:
                raise
            print(f"  {e}, retrying in {wait}s")
            time.sleep(wait)


def _ring(coords):
    return [(c["lon"], c["lat"]) for c in coords]


def _relation_shape(element):
    # polygons from outer ways
    lines = [LineString(_ring(m["geometry"])) for m in element.get("members", [])
             if m.get("type") == "way" and m.get("role") == "outer" and m.get("geometry")]
    polys = list(polygonize(linemerge(unary_union(lines)))) if lines else []
    return unary_union(polys) if polys else None


def _shape(element):
    if element["type"] == "node":
        return Point(element["lon"], element["lat"])
    if element["type"] == "way":
        coords = _ring(element["geometry"])
        closed = len(coords) >= 4 and coords[0] == coords[-1]
        if closed and element.get("tags", {}).get("power") == "substation":
            return Polygon(coords)
        return LineString(coords)
    return _relation_shape(element)


def overpass_to_gdf(elements):
    rows, shapes = [], []
    for el in elements:
        shape = _shape(el)
        if shape is None:
            continue
        rows.append({"osm_id": el["id"], "osm_type": el["type"], **el.get("tags", {})})
        shapes.append(shape)
    return gpd.GeoDataFrame(pd.DataFrame(rows), geometry=shapes, crs=4326)


def fetch_osm(get=get_json):
    s, w, n, e = BBOX
    area = f"({s},{w},{n},{e})"
    query = f"""
    [out:json][timeout:180];
    (
      node["power"~"^(pole|tower)$"]{area};
      way["power"~"^(line|minor_line)$"]{area};
      nwr["power"="substation"]{area};
    );
    out geom;
    """
    return overpass_to_gdf(get(OVERPASS_URL, {"data": query})["elements"])


def fetch_arcgis(url, bbox, get=get_json):
    s, w, n, e = bbox
    features, offset = [], 0
    while True:
        params = {
            "where": "1=1",
            "geometry": f"{w},{s},{e},{n}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "outSR": 4326,
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": PAGE_SIZE,
        }
        batch = get(f"{url}/query", params)["features"]
        features.extend(batch)
        # last page
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    if not features:
        return gpd.GeoDataFrame(geometry=[], crs=4326)
    return gpd.GeoDataFrame.from_features(features, crs=4326)


def _find_archive(archive_dir):
    for pattern in ("*ransmission*.gpkg", "*ransmission*.zip",
                    "*ransmission*.shp", "*ransmission*.geojson"):
        found = sorted(Path(archive_dir).glob(pattern))
        if found:
            return found[0]
    return None


def load_hifld(get=get_json, archive_dir=RAW):
    try:
        return fetch_arcgis(HIFLD_URL, BBOX, get=get)
    except Exception as e:
        print(f"  HIFLD service failed ({e}), trying the archived copy")
    path = _find_archive(archive_dir)
    if path is None:
        raise SystemExit(
            "HIFLD service is down and no archived copy was found.\n"
            f"Download the transmission lines file from {HIFLD_ARCHIVE_LINK}\n"
            f"(free login needed) and put it in {archive_dir}, then run again."
        )
    s, w, n, e = BBOX
    area = gpd.GeoSeries([box(w, s, e, n)], crs=4326)
    gdf = gpd.read_file(path, bbox=area).to_crs(4326)
    print(f"  using archived HIFLD copy {path.name}")
    return gdf


def save(gdf, name):
    RAW.mkdir(parents=True, exist_ok=True)
    final = RAW / f"{name}.geojson"
    tmp = RAW / f"{name}.tmp.geojson"
    # write to temp then rename
    gdf.to_file(tmp, driver="GeoJSON")
    tmp.replace(final)
    print(f"  saved {len(gdf)} features to {final}")


def main():
    print("OpenStreetMap power features")
    osm = fetch_osm()
    save(osm, "osm_power")
    print(osm["power"].value_counts().to_string())

    print("HIFLD transmission lines")
    save(load_hifld(), "hifld_lines")

    print("FEMA flood zones")
    save(fetch_arcgis(FEMA_URL, BBOX), "flood_zones")


if __name__ == "__main__":
    main()
