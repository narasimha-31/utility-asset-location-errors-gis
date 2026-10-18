import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL


def get_engine(database=None):
    load_dotenv()
    url = URL.create(
        "postgresql+psycopg",
        username=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        host=os.environ["PGHOST"],
        port=int(os.environ["PGPORT"]),
        database=database or os.environ["PGDATABASE"],
    )
    return create_engine(url)
