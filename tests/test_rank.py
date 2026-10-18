import pandas as pd

import report


HIGH = "POLYGON((0 0, 0 1000, 1000 1000, 1000 0, 0 0))"
MODERATE = "POLYGON((2000 0, 2000 1000, 3000 1000, 3000 0, 2000 0))"


def setup_zones_and_poles(qa):
    qa.add("flood_zones", HIGH, fld_zone="AE", zone_subty=None, sfha_tf="T")
    qa.add("flood_zones", MODERATE, fld_zone="X",
           zone_subty="0.2 PCT ANNUAL CHANCE FLOOD HAZARD", sfha_tf="F")
    # far away line so every pole gets flagged
    qa.add("osm_lines", "LINESTRING(0 50000, 1000 50000)", osm_id=1, power="line",
           voltage="138000", operator="Example Utility")
    qa.add("osm_supports", "POINT(500 500)", osm_id=11, power="pole", operator=None)
    qa.add("osm_supports", "POINT(2500 500)", osm_id=12, power="pole", operator=None)
    qa.add("osm_supports", "POINT(5000 500)", osm_id=13, power="pole", operator=None)
    qa.run("checks.sql", "rank.sql")


def test_errors_are_ranked_by_flood_zone(qa):
    setup_zones_and_poles(qa)
    rows = qa.query("SELECT feature_id, flood_rank, flood_zone FROM ranked_errors "
                    "WHERE check_name = 'support_not_on_line' ORDER BY priority")
    assert [(r["feature_id"], r["flood_rank"], r["flood_zone"]) for r in rows] == [
        ("11", 1, "AE"), ("12", 2, "X"), ("13", 3, None)]


def test_report_writes_csv_and_counts(qa, tmp_path):
    setup_zones_and_poles(qa)
    summary = report.write_report(qa.engine, out_dir=tmp_path)
    csv = pd.read_csv(tmp_path / "error_report.csv")
    assert len(csv) == summary["total"]
    assert summary["by_check"]["support_not_on_line"] == 3
    assert summary["by_flood_rank"] == {1: 1, 2: 1, 3: summary["total"] - 2}
    assert {"priority", "check_name", "flood_rank", "lon", "lat"} <= set(csv.columns)
