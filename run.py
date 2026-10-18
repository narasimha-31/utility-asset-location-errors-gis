from pathlib import Path

from db import get_engine


def run_sql(engine, path, schema="public"):
    sql = Path(path).read_text()
    with engine.begin() as conn:
        cur = conn.connection.cursor()
        cur.execute(f"SET search_path TO {schema}, public")
        # multi-statement file, no params
        cur.execute(sql)


def main():
    import load

    engine = get_engine()
    print("loading tables")
    for table, count in load.load_all(engine).items():
        print(f"  {table}: {count}")
    print("running checks")
    run_sql(engine, "checks.sql")


if __name__ == "__main__":
    main()
