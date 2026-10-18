from pathlib import Path

from db import get_engine


def run_sql(engine, path):
    sql = Path(path).read_text()
    with engine.begin() as conn:
        cur = conn.connection.cursor()
        # multi-statement file, no params
        cur.execute(sql)


def main():
    import load
    import report

    engine = get_engine()
    print("loading tables")
    for table, count in load.load_all(engine).items():
        print(f"  {table}: {count}")
    print("running checks")
    run_sql(engine, "checks.sql")
    print("ranking by flood zone")
    run_sql(engine, "rank.sql")
    print("writing report\n")
    report.print_summary(report.write_report(engine))


if __name__ == "__main__":
    main()
