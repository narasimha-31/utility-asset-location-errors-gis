from sqlalchemy import text

from db import get_engine


def test_postgis_available():
    with get_engine().connect() as conn:
        version = conn.execute(text("SELECT postgis_version()")).scalar()
    assert version.startswith("3.5")
