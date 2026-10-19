#!/usr/bin/env python3
"""Check a PyPika checkout against the safety properties this fork claims to fix.

Run it against any checkout to get a PASS/FAIL table:

    python tools/upstream_compare.py /path/to/pypika

It only uses public API that exists in upstream 0.51.1, so the same script runs
against both the original project and this fork.  Every property is phrased as an
observable behaviour (rendered SQL, or rows returned by a real SQLite database),
never as "the function exists".
"""

from __future__ import annotations

import argparse
import datetime
import sqlite3
import sys
import traceback
from typing import Any, Callable


class Check:
    def __init__(self, name: str, fn: Callable[[], None]) -> None:
        self.name = name
        self.fn = fn


def build_checks(pypika_mod: Any, mysql_q: Any, pg_q: Any, query: Any, table: Any, qmark: Any) -> list[Check]:
    T = table("users")
    checks: list[Check] = []

    def check(name):
        def deco(fn):
            checks.append(Check(name, fn))
            return fn

        return deco

    @check("MySQL: trailing backslash cannot escape the closing quote")
    def _() -> None:
        sql = mysql_q.from_(T).select(T.star).where(T.name == "a\\").get_sql()
        assert "a\\\\'" in sql, f"backslash not doubled: {sql}"

    @check("MySQL: \\' payload cannot terminate the literal")
    def _() -> None:
        sql = mysql_q.from_(T).select(T.star).where(T.name == "x\\' OR 1=1 -- ").get_sql()
        body = sql[sql.index("='") + 2 : sql.rindex("'")]
        stripped = body.replace("\\\\", "")
        assert "\\'" not in stripped, f"payload still has an escaping backslash: {sql}"

    @check("ANSI: backslash stays verbatim (no behaviour change)")
    def _() -> None:
        sql = pg_q.from_(T).select(T.star).where(T.name == "a\\").get_sql()
        assert "'a\\'" in sql, f"ANSI escaping changed unexpectedly: {sql}"

    @check("MySQL: control characters are named, not embedded raw")
    def _() -> None:
        sql = mysql_q.from_(T).select(T.star).where(T.name == "a\nb").get_sql()
        assert "\\n" in sql, f"newline not escaped: {sql!r}"

    @check("bytes are rejected instead of leaking repr()")
    def _() -> None:
        try:
            query.from_(T).select(T.star).where(T.blob == b"abc").get_sql()
        except Exception:
            return
        raise AssertionError("bytes were silently rendered")

    @check("== None renders IS NULL")
    def _() -> None:
        sql = query.from_(T).select("*").where(T.deleted_at == None).get_sql()  # noqa: E711
        assert "IS NULL" in sql, f"got {sql}"

    @check("!= None renders IS NOT NULL")
    def _() -> None:
        sql = query.from_(T).select("*").where(T.deleted_at != None).get_sql()  # noqa: E711
        assert "IS NOT NULL" in sql, f"got {sql}"

    @check("== None actually returns the NULL rows (real SQLite)")
    def _() -> None:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE users(id INTEGER, name TEXT, deleted_at TEXT)")
        conn.executemany("INSERT INTO users VALUES(?,?,?)", [(1, "a", None), (2, "b", "x"), (3, "c", None)])
        sql = query.from_(T).select(T.id).where(T.deleted_at == None).get_sql()  # noqa: E711
        rows = sorted(r[0] for r in conn.execute(sql))
        conn.close()
        assert rows == [1, 3], f"expected [1, 3], got {rows} via {sql}"

    @check("empty isin() is not `IN ()`")
    def _() -> None:
        sql = query.from_(T).select("*").where(T.id.isin([])).get_sql()
        assert "IN ()" not in sql, f"invalid empty IN still emitted: {sql}"

    @check("empty isin() matches nothing (real SQLite)")
    def _() -> None:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE users(id INTEGER)")
        conn.executemany("INSERT INTO users VALUES(?)", [(1,), (2,)])
        sql = query.from_(T).select(T.id).where(T.id.isin([])).get_sql()
        rows = conn.execute(sql).fetchall()
        conn.close()
        assert rows == [], f"expected no rows, got {rows} via {sql}"

    @check("isin([1, None]) is refused rather than silently matching nothing")
    def _() -> None:
        try:
            sql = query.from_(T).select("*").where(T.id.isin([1, None])).get_sql()
        except Exception:
            return
        raise AssertionError(f"ambiguous IN with NULL was emitted: {sql}")

    @check("bound parameters carry Python values, not SQL fragments")
    def _() -> None:
        parameter = qmark()
        query.from_(T).select("*").where(T.c == "foobar").get_sql(parameter=parameter)
        got = parameter.get_parameters()[0]
        assert got == "foobar", f"string parameter was pre-quoted: {got!r}"

    @check("bound parameters keep date type")
    def _() -> None:
        parameter = qmark()
        value = datetime.date(2024, 2, 22)
        query.from_(T).select("*").where(T.c == value).get_sql(parameter=parameter)
        got = parameter.get_parameters()[0]
        assert isinstance(got, datetime.date), f"date became {type(got).__name__}: {got!r}"

    @check("bound parameters keep bytes type")
    def _() -> None:
        parameter = qmark()
        query.from_(T).select("*").where(T.c == b"abc").get_sql(parameter=parameter)
        got = parameter.get_parameters()[0]
        assert isinstance(got, bytes), f"bytes became {type(got).__name__}: {got!r}"

    @check("LIKE pattern helper exists and escapes wildcards")
    def _() -> None:
        assert hasattr(T.name, "like_literal"), "like_literal() missing"
        sql = query.from_(T).select("*").where(T.name.like_literal("100%_off")).get_sql()
        assert "ESCAPE" in sql and "\\%" in sql, f"wildcards not escaped: {sql}"

    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkout", help="path to a pypika source checkout")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    sys.path.insert(0, args.checkout)

    import pypika
    from pypika import MySQLQuery, PostgreSQLQuery, Query, Table
    from pypika.terms import QmarkParameter

    checks = build_checks(pypika, MySQLQuery, PostgreSQLQuery, Query, Table, QmarkParameter)

    passed = failed = 0
    print(f"target : {args.checkout}")
    print(f"version: {getattr(pypika, '__version__', '?')}")
    print("-" * 78)
    for chk in checks:
        try:
            chk.fn()
        except AssertionError as exc:
            failed += 1
            print(f"FAIL  {chk.name}")
            if args.verbose:
                print(f"      {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"ERROR {chk.name}")
            if args.verbose:
                print(f"      {type(exc).__name__}: {exc}")
                traceback.print_exc(limit=1)
        else:
            passed += 1
            print(f"PASS  {chk.name}")
    print("-" * 78)
    print(f"{passed} passed, {failed} failed, {passed + failed} total")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
