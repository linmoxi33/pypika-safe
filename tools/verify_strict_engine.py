"""Verify the empty-IN fix against a strict SQL engine (DuckDB).

SQLite accepts ``IN ()`` as a non-standard extension, so it cannot prove the fix
matters.  DuckDB follows the standard and raises a parser error, which is what
PostgreSQL / Oracle / MSSQL also do.
"""

import duckdb

from pypika import Query, Table

t = Table("users")


def main() -> int:
    conn = duckdb.connect()
    conn.execute("CREATE TABLE users(id INTEGER, name VARCHAR, deleted_at VARCHAR)")
    conn.executemany("INSERT INTO users VALUES (?,?,?)", [(1, "alice", None), (2, "bob", "x"), (3, "carol", None)])

    ok = True

    # 1. the upstream shape `IN ()` must fail on a strict engine
    raw = 'SELECT * FROM "users" WHERE "id" IN ()'
    try:
        conn.execute(raw).fetchall()
        print(f"UNEXPECTED: strict engine accepted {raw}")
        ok = False
    except Exception as exc:  # noqa: BLE001
        print(f"baseline rejected as expected: {type(exc).__name__} for `IN ()`")

    # 2. the fork's rendering must be accepted and mean "match nothing"
    q = Query.from_(t).select(t.id).where(t.id.isin([]))
    sql = q.get_sql()
    rows = conn.execute(sql).fetchall()
    print(f"fork SQL: {sql}")
    print(f"rows    : {rows}")
    if rows != []:
        print("FAIL: empty IN should match nothing")
        ok = False

    # 3. empty NOT IN must match everything
    q2 = Query.from_(t).select(t.id).where(t.id.notin([]))
    sql2 = q2.get_sql()
    rows2 = sorted(r[0] for r in conn.execute(sql2).fetchall())
    print(f"fork SQL: {sql2}")
    print(f"rows    : {rows2}")
    if rows2 != [1, 2, 3]:
        print("FAIL: empty NOT IN should match everything")
        ok = False

    # 4. IS NULL rendering must run and return the null rows
    q3 = Query.from_(t).select(t.id).where(t.deleted_at == None)  # noqa: E711
    sql3 = q3.get_sql()
    rows3 = sorted(r[0] for r in conn.execute(sql3).fetchall())
    print(f"fork SQL: {sql3}")
    print(f"rows    : {rows3}")
    if rows3 != [1, 3]:
        print("FAIL: IS NULL should return the null rows")
        ok = False

    # 5. the upstream `=null` shape returns nothing on a real engine (documents the bug)
    raw_null = 'SELECT "id" FROM "users" WHERE "deleted_at"=null'
    rows4 = conn.execute(raw_null).fetchall()
    print(f"baseline `=null` rows: {rows4}  (silently empty = the bug)")

    conn.close()
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
