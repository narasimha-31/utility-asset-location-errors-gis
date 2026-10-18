import pytest

CHECKS = "checks.sql"


def add_osm_line(qa, osm_id, wkt, voltage="138000", operator="Example Utility", power="line"):
    qa.add("osm_lines", wkt, osm_id=osm_id, power=power, voltage=voltage, operator=operator)


def add_hifld(qa, line_id, wkt, from_osm=False, voltage=138):
    qa.add("hifld_lines", wkt, id=line_id, owner="Example Utility", voltage=voltage,
           source="IMAGERY", from_osm=from_osm)


def test_hifld_line_150_ft_from_osm_is_a_disagreement(qa):
    add_osm_line(qa, 1, "LINESTRING(0 0, 5000 0)")
    add_hifld(qa, "h1", "LINESTRING(0 150, 5000 150)")
    qa.run(CHECKS)
    found = qa.errors("osm_hifld_disagreement")
    assert len(found) == 1
    assert found[0]["feature_id"] == "h1"
    assert float(found[0]["size_ft"]) == pytest.approx(150, abs=1)


def test_hifld_line_40_ft_from_osm_agrees(qa):
    add_osm_line(qa, 1, "LINESTRING(0 0, 5000 0)")
    add_hifld(qa, "h1", "LINESTRING(0 40, 5000 40)")
    qa.run(CHECKS)
    assert qa.errors("osm_hifld_disagreement") == []


def test_hifld_line_copied_from_osm_is_skipped(qa):
    add_osm_line(qa, 1, "LINESTRING(0 0, 5000 0)")
    add_hifld(qa, "h1", "LINESTRING(0 150, 5000 150)", from_osm=True)
    qa.run(CHECKS)
    assert qa.errors("osm_hifld_disagreement") == []


def test_hifld_line_with_no_osm_line_nearby_says_not_found(qa):
    add_osm_line(qa, 1, "LINESTRING(0 0, 5000 0)")
    add_hifld(qa, "h1", "LINESTRING(0 5000, 5000 5000)")
    qa.run(CHECKS)
    found = qa.errors("osm_hifld_disagreement")
    assert len(found) == 1
    assert "not found in OSM" in found[0]["detail"]


def test_distribution_lines_are_not_used_for_location_check(qa):
    add_osm_line(qa, 1, "LINESTRING(0 0, 5000 0)", power="minor_line")
    add_hifld(qa, "h1", "LINESTRING(0 40, 5000 40)")
    qa.run(CHECKS)
    # hifld is transmission only
    assert len(qa.errors("osm_hifld_disagreement")) == 1


def add_support(qa, osm_id, wkt, power="pole"):
    qa.add("osm_supports", wkt, osm_id=osm_id, power=power, operator=None)


def add_substation(qa, osm_id, wkt):
    qa.add("osm_substations", wkt, osm_id=osm_id, name=None, operator=None)


def test_pole_on_a_line_is_fine(qa):
    add_osm_line(qa, 1, "LINESTRING(0 0, 1000 0)")
    add_support(qa, 10, "POINT(500 0)")
    qa.run(CHECKS)
    assert qa.errors("support_not_on_line") == []


def test_pole_20_ft_from_a_line_is_flagged(qa):
    add_osm_line(qa, 1, "LINESTRING(0 0, 1000 0)")
    add_support(qa, 10, "POINT(500 20)")
    qa.run(CHECKS)
    found = qa.errors("support_not_on_line")
    assert [f["feature_id"] for f in found] == ["10"]
    assert float(found[0]["size_ft"]) == pytest.approx(20)


def test_lines_that_reach_a_substation_are_connected(qa):
    add_substation(qa, 50, "POLYGON((-100 -100, -100 100, 0 100, 0 -100, -100 -100))")
    add_osm_line(qa, 1, "LINESTRING(0 0, 1000 0)")
    add_osm_line(qa, 2, "LINESTRING(1000 0, 2000 500)")
    qa.run(CHECKS)
    assert qa.errors("possible_mapping_gap") == []


def test_lines_that_never_reach_a_substation_are_a_possible_gap(qa):
    add_substation(qa, 50, "POLYGON((-100 -100, -100 100, 0 100, 0 -100, -100 -100))")
    add_osm_line(qa, 1, "LINESTRING(0 0, 1000 0)")
    add_osm_line(qa, 2, "LINESTRING(5000 0, 6000 0)")
    add_osm_line(qa, 3, "LINESTRING(6000 0, 7000 0)")
    qa.run(CHECKS)
    assert [f["feature_id"] for f in qa.errors("possible_mapping_gap")] == ["2", "3"]


def test_lines_leaving_the_study_area_are_not_flagged(qa):
    add_osm_line(qa, 1, "LINESTRING(99000 0, 101000 0)")
    qa.run(CHECKS)
    assert qa.errors("possible_mapping_gap") == []
