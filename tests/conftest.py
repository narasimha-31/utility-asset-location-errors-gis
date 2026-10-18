import pytest
from sqlalchemy import text

from db import get_engine
import run

# checks drop tables
TEST_DATABASE = "gis_test"

TABLES = """
DROP TABLE IF EXISTS osm_supports, osm_lines, osm_substations, hifld_lines, flood_zones,
    study_area, errors, ranked_errors CASCADE;
CREATE TABLE osm_supports (osm_id bigint, power text, operator text, geom geometry(Point, 2278));
CREATE TABLE osm_lines (osm_id bigint, power text, voltage text, operator text, geom geometry(LineString, 2278));
CREATE TABLE osm_substations (osm_id bigint, name text, operator text, geom geometry(Geometry, 2278));
CREATE TABLE hifld_lines (id text, owner text, voltage numeric, source text, from_osm boolean, geom geometry(Geometry, 2278));
CREATE TABLE flood_zones (fld_zone text, zone_subty text, sfha_tf text, geom geometry(Geometry, 2278));
CREATE TABLE study_area (geom geometry(Polygon, 2278));
INSERT INTO study_area VALUES (ST_MakeEnvelope(-100000, -100000, 100000, 100000, 2278));
"""


class QA:
    def __init__(self, engine):
        self.engine = engine

    def add(self, table, wkt, **cols):
        names = ", ".join(list(cols) + ["geom"])
        marks = ", ".join([f":{c}" for c in cols] + ["ST_GeomFromText(:wkt, 2278)"])
        with self.engine.begin() as conn:
            conn.execute(text(f"INSERT INTO {table} ({names}) VALUES ({marks})"),
                         {**cols, "wkt": wkt})

    def run(self, *files):
        for path in files:
            run.run_sql(self.engine, path)

    def errors(self, check):
        with self.engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT * FROM errors WHERE check_name = :c ORDER BY feature_id"), {"c": check})
            return [dict(r._mapping) for r in rows]

    def query(self, sql):
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(text(sql))]


@pytest.fixture(scope="session")
def test_engine():
    admin = get_engine().execution_options(isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :d"),
                              {"d": TEST_DATABASE}).scalar()
        if not exists:
            conn.execute(text(f"CREATE DATABASE {TEST_DATABASE}"))
    engine = get_engine(TEST_DATABASE)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    return engine


@pytest.fixture
def qa(test_engine):
    with test_engine.begin() as conn:
        conn.exec_driver_sql(TABLES)
    return QA(test_engine)
