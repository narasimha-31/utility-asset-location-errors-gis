import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

from db import get_engine

OUTPUT = Path("output")
FLOOD_LABELS = {1: "high risk flood zone", 2: "0.2 percent annual chance zone", 3: "outside flood zones"}
# same colors as the qgis map
CHECK_COLORS = {
    "osm_hifld_disagreement": "#d7191c",
    "possible_mapping_gap": "#fd8d3c",
    "support_not_on_line": "#7b3294",
    "voltage_disagreement": "#008837",
    "missing_voltage": "#525252",
    "missing_operator": "#bdbdbd",
}


def write_report(engine, out_dir=OUTPUT):
    errors = gpd.read_postgis("SELECT * FROM ranked_errors ORDER BY priority",
                              engine, geom_col="geom")
    lonlat = errors.geometry.to_crs(4326)
    errors["lon"] = lonlat.x.round(6)
    errors["lat"] = lonlat.y.round(6)
    errors["x_ft"] = errors.geometry.x.round(1)
    errors["y_ft"] = errors.geometry.y.round(1)
    errors["flood_risk"] = errors["flood_rank"].map(FLOOD_LABELS)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    columns = ["priority", "check_name", "feature_type", "feature_id", "detail", "size_ft",
               "flood_rank", "flood_risk", "flood_zone", "lon", "lat", "x_ft", "y_ft"]
    errors[columns].to_csv(out_dir / "error_report.csv", index=False)
    write_geojson(errors, out_dir / "findings.geojson")

    return {
        "total": len(errors),
        "by_check": errors["check_name"].value_counts().to_dict(),
        "by_flood_rank": {int(k): int(v) for k, v in
                          errors["flood_rank"].value_counts().sort_index().items()},
        "by_check_and_flood_rank": errors.pivot_table(
            index="check_name", columns="flood_rank", values="priority",
            aggfunc="count", fill_value=0),
    }


def write_geojson(errors, path):
    # github renders this as a map, it needs plain lon/lat
    features = []
    for row in errors.itertuples():
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(row.lon), float(row.lat)]},
            "properties": {
                "priority": int(row.priority),
                "check": row.check_name,
                "feature": f"{row.feature_type} {row.feature_id}",
                "detail": row.detail,
                "size_ft": None if pd.isna(row.size_ft) else float(row.size_ft),
                "flood_zone": "none" if pd.isna(row.flood_zone) else row.flood_zone,
                "marker-color": CHECK_COLORS.get(row.check_name, "#000000"),
                "marker-size": "large" if row.flood_rank == 1 else "small",
            },
        })
    # one feature per line keeps git diffs readable
    body = ",\n".join(json.dumps(f, separators=(",", ":")) for f in features)
    Path(path).write_text('{"type":"FeatureCollection","features":[\n' + body + "\n]}\n")


def print_summary(summary):
    print(f"total flagged: {summary['total']}")
    print("\nby check and flood rank (1 = high risk, 2 = 0.2 percent, 3 = outside)")
    print(summary["by_check_and_flood_rank"].to_string())


if __name__ == "__main__":
    print_summary(write_report(get_engine()))
