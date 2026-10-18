from sqlalchemy import text

from db import get_engine


def test_postgis_available():
    with get_engine().connect() as conn:
        version = conn.execute(text("SELECT postgis_version()")).scalar()
    assert version.startswith("3.5")


def test_check_tests_use_their_own_database(qa):
    assert qa.engine.url.database != get_engine().url.database
