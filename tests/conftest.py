import pytest
from sqlalchemy import text

from db import get_engine
import run

SCHEMA = "qa_test"

TABLES = f"""
CREATE TABLE {SCHEMA}.osm_supports (osm_id bigint, power text, operator text, geom geometry(Point, 2278));
CREATE TABLE {SCHEMA}.osm_lines (osm_id bigint, power text, voltage text, operator text, geom geometry(LineString, 2278));
CREATE TABLE {SCHEMA}.osm_substations (osm_id bigint, name text, operator text, geom geometry(Geometry, 2278));
CREATE TABLE {SCHEMA}.hifld_lines (id text, owner text, voltage numeric, source text, from_osm boolean, geom geometry(Geometry, 2278));
CREATE TABLE {SCHEMA}.flood_zones (fld_zone text, zone_subty text, sfha_tf text, geom geometry(Geometry, 2278));
CREATE TABLE {SCHEMA}.study_area (geom geometry(Polygon, 2278));
INSERT INTO {SCHEMA}.study_area VALUES (ST_MakeEnvelope(-100000, -100000, 100000, 100000, 2278));
"""


class QA:
    def __init__(self, engine):
        self.engine = engine

    def add(self, table, wkt, **cols):
        names = ", ".join(list(cols) + ["geom"])
        marks = ", ".join([f":{c}" for c in cols] + ["ST_GeomFromText(:wkt, 2278)"])
        with self.engine.begin() as conn:
            conn.execute(text(f"INSERT INTO {SCHEMA}.{table} ({names}) VALUES ({marks})"),
                         {**cols, "wkt": wkt})

    def run(self, *files):
        for path in files:
            run.run_sql(self.engine, path, schema=SCHEMA)

    def errors(self, check):
        with self.engine.connect() as conn:
            rows = conn.execute(text(
                f"SELECT * FROM {SCHEMA}.errors WHERE check_name = :c ORDER BY feature_id"
            ), {"c": check})
            return [dict(r._mapping) for r in rows]

    def query(self, sql):
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(text(sql))]


@pytest.fixture
def qa():
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        conn.exec_driver_sql(TABLES)
    yield QA(engine)
    with engine.begin() as conn:
        conn.execute(text(f"DROP SCHEMA {SCHEMA} CASCADE"))
