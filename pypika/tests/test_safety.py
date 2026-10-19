"""Tests for the dialect-aware literal / criterion safety layer.

These tests are written to fail on upstream PyPika 0.51.1 and pass on this fork.
Where a property is expressible as "does the database actually return the right
rows", the test runs against a real in-memory SQLite database instead of only
comparing SQL strings.
"""

from __future__ import annotations

import datetime
import decimal
import sqlite3
import unittest
import uuid
from unittest import TestCase

from pypika import (
    ClickHouseQuery,
    MySQLQuery,
    PostgreSQLQuery,
    Query,
    Table,
    UnsafeIdentifierError,
    UnsafeLiteralError,
    AmbiguousNullCriterionError,
    assert_safe_identifiers,
    escape_like_pattern,
    escape_string_literal,
    like_escape_clause,
)
from pypika.enums import Dialects
from pypika.terms import QmarkParameter, FormatParameter, NamedParameter, PyformatParameter


class EscapeStringLiteralTests(TestCase):
    """The core primitive: one string, three dialect families."""

    def test_ansi_escapes_only_the_quote(self):
        self.assertEqual("'O''Brien'", escape_string_literal("O'Brien", dialect=None))
        self.assertEqual("'a\\b'", escape_string_literal("a\\b", dialect=None))

    def test_ansi_dialects_are_all_treated_as_ansi(self):
        for dialect in (
            Dialects.POSTGRESQL,
            Dialects.SQLLITE,
            Dialects.ORACLE,
            Dialects.MSSQL,
            Dialects.SNOWFLAKE,
            Dialects.VERTICA,
            Dialects.REDSHIFT,
        ):
            with self.subTest(dialect=dialect):
                self.assertEqual("'a\\b'", escape_string_literal("a\\b", dialect=dialect))

    def test_backslash_dialects_escape_the_backslash(self):
        # The trailing backslash must not be able to escape the closing quote.
        self.assertEqual("'a\\\\'", escape_string_literal("a\\", dialect=Dialects.MYSQL))
        self.assertEqual("'a\\\\'", escape_string_literal("a\\", dialect=Dialects.CLICKHOUSE))

    def test_backslash_dialect_payload_cannot_break_out(self):
        payload = "x\\' OR 1=1 -- "
        rendered = escape_string_literal(payload, dialect=Dialects.MYSQL)
        # The backslash is doubled, so the quote that follows it is no longer escaped and
        # the quote is doubled too: the literal has exactly two interior quote characters
        # and the payload can never terminate it.
        self.assertEqual("'x\\\\'' OR 1=1 -- '", rendered)
        body = rendered[1:-1]
        self.assertNotIn("\\'", body.replace("\\\\", ""), "a lone backslash must not precede a quote")

    def test_control_characters_are_named_in_backslash_dialects(self):
        self.assertEqual("'a\\nb'", escape_string_literal("a\nb", dialect=Dialects.MYSQL))
        self.assertEqual("'a\\rb'", escape_string_literal("a\rb", dialect=Dialects.MYSQL))
        self.assertEqual("'a\\tb'", escape_string_literal("a\tb", dialect=Dialects.MYSQL))
        self.assertEqual("'a\\Zb'", escape_string_literal("a\x1ab", dialect=Dialects.MYSQL))
        self.assertEqual("'a\\0b'", escape_string_literal("a\x00b", dialect=Dialects.MYSQL))

    def test_nul_byte_is_rejected_in_ansi_dialects(self):
        # PostgreSQL refuses NUL in text literals and a driver would truncate the value,
        # so silently emitting it is worse than failing loudly.
        with self.assertRaises(UnsafeLiteralError):
            escape_string_literal("a\x00b", dialect=Dialects.POSTGRESQL)
        with self.assertRaises(UnsafeLiteralError):
            escape_string_literal("a\x00b", dialect=None)

    def test_custom_quote_char_is_honoured(self):
        self.assertEqual('"a""b"', escape_string_literal('a"b', quote_char='"', dialect=None))
        # Doubling works in both sql_modes, so the quote is always doubled rather than
        # backslash-escaped; only the backslash itself needs special handling.
        self.assertEqual('"a""b"', escape_string_literal('a"b', quote_char='"', dialect=Dialects.MYSQL))
        self.assertEqual('"a\\\\b"', escape_string_literal("a\\b", quote_char='"', dialect=Dialects.MYSQL))

    def test_empty_string(self):
        self.assertEqual("''", escape_string_literal("", dialect=Dialects.MYSQL))
        self.assertEqual("''", escape_string_literal("", dialect=None))

    def test_non_string_rejected(self):
        with self.assertRaises(TypeError):
            escape_string_literal(123, dialect=None)

    def test_missing_quote_char_rejected(self):
        with self.assertRaises(ValueError):
            escape_string_literal("abc", quote_char="", dialect=None)

    def test_backslash_escapes_override_disables_doubling(self):
        # MySQL with NO_BACKSLASH_ESCAPES: a backslash is literal, doubling it would
        # change the stored value.
        self.assertEqual(
            "'a\\'",
            escape_string_literal("a\\", dialect=Dialects.MYSQL, backslash_escapes=False),
        )

    def test_backslash_escapes_override_enables_doubling(self):
        self.assertEqual(
            "'a\\\\'",
            escape_string_literal("a\\", dialect=Dialects.POSTGRESQL, backslash_escapes=True),
        )


class QueryLiteralEmissionTests(TestCase):
    """The escaper must actually be reachable from a built query."""

    t = Table("users")

    def test_mysql_query_uses_backslash_escaping(self):
        sql = MySQLQuery.from_(self.t).select(self.t.star).where(self.t.name == "a\\").get_sql()
        self.assertEqual("SELECT * FROM `users` WHERE `name`='a\\\\'", sql)

    def test_dialect_kwarg_on_a_plain_query_is_honoured(self):
        # ``Query.from_(...).get_sql(dialect=Dialects.MYSQL)`` must escape like MySQL even
        # though the builder itself is dialect-agnostic.
        sql = Query.from_(self.t).select(self.t.star).where(self.t.name == "a\\").get_sql(dialect=Dialects.MYSQL)
        self.assertIn("'a\\\\'", sql)

    def test_backslash_escapes_kwarg_reaches_the_escaper(self):
        sql = MySQLQuery.from_(self.t).select(self.t.star).where(self.t.name == "a\\").get_sql(backslash_escapes=False)
        self.assertIn("'a\\'", sql)

    def test_clickhouse_query_uses_backslash_escaping(self):
        sql = ClickHouseQuery.from_(self.t).select(self.t.star).where(self.t.name == "a\\").get_sql()
        self.assertEqual("SELECT * FROM \"users\" WHERE \"name\"='a\\\\'", sql)

    def test_postgres_query_keeps_backslash_verbatim(self):
        sql = PostgreSQLQuery.from_(self.t).select(self.t.star).where(self.t.name == "a\\").get_sql()
        self.assertEqual('SELECT * FROM "users" WHERE "name"=\'a\\\'', sql)

    def test_str_of_mysql_query_is_escaped(self):
        # ``str(query)`` goes through get_sql(dialect=...), so it must not regress.
        self.assertEqual(
            "SELECT * FROM `users` WHERE `name`='a\\\\'",
            str(MySQLQuery.from_(self.t).select(self.t.star).where(self.t.name == "a\\")),
        )

    def test_insert_values_are_escaped(self):
        sql = MySQLQuery.into(self.t).columns("name").insert("a\\").get_sql()
        self.assertIn("'a\\\\'", sql)

    def test_update_values_are_escaped(self):
        sql = MySQLQuery.update(self.t).set("name", "a\\").get_sql()
        self.assertIn("'a\\\\'", sql)

    def test_json_literal_is_escaped(self):
        import re

        from pypika.terms import JSON

        # A trailing backslash inside a JSON string must not be able to escape the
        # closing quote of the surrounding literal.
        sql = MySQLQuery.from_(self.t).select(JSON({"k": "a\\"})).get_sql()
        body = sql[sql.index("'") + 1 : sql.rindex("'")]
        runs = re.findall(r"\\+", body)
        self.assertTrue(runs, "expected backslashes in the rendered JSON literal")
        self.assertTrue(all(len(run) % 2 == 0 for run in runs), f"odd backslash run in {body!r}")

    def test_bytes_are_rejected_instead_of_repr_leaked(self):
        # Upstream rendered b'abc' as the string "b'abc'", which silently corrupts data.
        with self.assertRaises(UnsafeLiteralError):
            Query.from_(self.t).select(self.t.star).where(self.t.blob == b"abc").get_sql()


class InjectionShapeTests(TestCase):
    """Parse the generated SQL and assert the payload never becomes a new AST node."""

    t = Table("users")
    PAYLOADS = (
        "O'Brien",
        "a\\",
        "x\\' OR 1=1 -- ",
        'a"b',
        "line1\nline2",
        "a\tb",
        "a\x1ab",
        "名字 'quoted'",
        "\\'; DROP TABLE users; --",
        "'; SELECT * FROM secrets; --",
    )

    def test_mysql_payloads_stay_single_literal(self):
        try:
            import sqlglot
            from sqlglot import exp
        except ImportError:  # pragma: no cover - optional dev dependency
            self.skipTest("sqlglot not installed")

        for payload in self.PAYLOADS:
            with self.subTest(payload=payload):
                sql = MySQLQuery.from_(self.t).select(self.t.star).where(self.t.name == payload).get_sql()
                tree = sqlglot.parse_one(sql, dialect="mysql")
                self.assertEqual(0, len(list(tree.find_all(exp.Or))), f"payload {payload!r} produced an OR")
                self.assertEqual(0, len(list(tree.find_all(exp.Drop))), f"payload {payload!r} produced a DROP")
                self.assertEqual(1, len(list(tree.find_all(exp.Select))), f"payload {payload!r} produced a second SELECT")
                literals = [node.this for node in tree.find_all(exp.Literal) if node.is_string]
                self.assertEqual([payload], literals, "literal did not round-trip")

    def test_ansi_payloads_stay_single_literal(self):
        try:
            import sqlglot
            from sqlglot import exp
        except ImportError:  # pragma: no cover
            self.skipTest("sqlglot not installed")

        for payload in self.PAYLOADS:
            with self.subTest(payload=payload):
                sql = PostgreSQLQuery.from_(self.t).select(self.t.star).where(self.t.name == payload).get_sql()
                tree = sqlglot.parse_one(sql, dialect="postgres")
                self.assertEqual(0, len(list(tree.find_all(exp.Or))))
                literals = [node.this for node in tree.find_all(exp.Literal) if node.is_string]
                self.assertEqual([payload], literals)


class RealDatabaseTests(TestCase):
    """End-to-end: run the generated SQL against a real engine and check the rows."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE users(id INTEGER, name TEXT, deleted_at TEXT)")
        self.conn.executemany(
            "INSERT INTO users VALUES(?,?,?)",
            [
                (1, "alice", None),
                (2, "bob", "2026-01-01"),
                (3, "carol", None),
                (4, "100%_off", "2026-01-02"),
            ],
        )
        self.t = Table("users")

    def tearDown(self):
        self.conn.close()

    def _ids(self, query):
        return sorted(row[0] for row in self.conn.execute(query.get_sql()))

    def test_injection_payload_matches_nothing(self):
        payload = "x\\' OR 1=1 -- "
        q = Query.from_(self.t).select(self.t.id).where(self.t.name == payload)
        self.assertEqual([], self._ids(q))

    def test_injection_payload_does_not_widen_result_set(self):
        # Even in the ANSI dialect, where the backslash is literal, the quote doubling
        # must keep the comparison to an exact match.
        payload = "alice' OR '1'='1"
        q = Query.from_(self.t).select(self.t.id).where(self.t.name == payload)
        self.assertEqual([], self._ids(q))

    def test_equals_none_returns_null_rows(self):
        q = Query.from_(self.t).select(self.t.id).where(self.t.deleted_at == None)  # noqa: E711
        self.assertEqual([1, 3], self._ids(q))
        self.assertIn("IS NULL", q.get_sql())

    def test_not_equals_none_returns_non_null_rows(self):
        q = Query.from_(self.t).select(self.t.id).where(self.t.deleted_at != None)  # noqa: E711
        self.assertEqual([2, 4], self._ids(q))
        self.assertIn("IS NOT NULL", q.get_sql())

    def test_like_literal_matches_wildcards_literally(self):
        q = Query.from_(self.t).select(self.t.id).where(self.t.name.like_literal("100%_off"))
        self.assertEqual([4], self._ids(q))

    def test_plain_like_treats_them_as_wildcards(self):
        # Documents the difference: the old behaviour is still available and still wildcard-y.
        q = Query.from_(self.t).select(self.t.id).where(self.t.name.like("100%_off"))
        self.assertEqual([4], self._ids(q))
        q2 = Query.from_(self.t).select(self.t.id).where(self.t.name.like("100%off"))
        self.assertEqual([4], self._ids(q2), "% still matches any run of characters")

    def test_empty_isin_matches_nothing(self):
        q = Query.from_(self.t).select(self.t.id).where(self.t.id.isin([]))
        self.assertEqual([], self._ids(q))
        self.assertEqual("1=0", q.get_sql().split("WHERE ")[1])

    def test_empty_notin_matches_everything(self):
        q = Query.from_(self.t).select(self.t.id).where(self.t.id.notin([]))
        self.assertEqual([1, 2, 3, 4], self._ids(q))

    def test_empty_isin_inside_and_keeps_precedence(self):
        q = Query.from_(self.t).select(self.t.id).where(self.t.id > 1).where(self.t.name.isin([]))
        self.assertEqual([], self._ids(q))
        self.assertIn("AND 1=0", q.get_sql())

    def test_empty_isin_inside_or_keeps_precedence(self):
        q = Query.from_(self.t).select(self.t.id).where((self.t.name == "alice") | self.t.name.isin([]))
        self.assertEqual([1], self._ids(q))
        self.assertIn("OR 1=0", q.get_sql())

    def test_empty_isin_under_not_matches_everything(self):
        q = Query.from_(self.t).select(self.t.id).where(~self.t.name.isin([]))
        self.assertEqual([1, 2, 3, 4], self._ids(q))


class NullCriterionTests(TestCase):
    t = Table("users")

    def test_eq_none_renders_is_null(self):
        self.assertEqual(
            'SELECT * FROM "users" WHERE "deleted_at" IS NULL',
            Query.from_(self.t).select("*").where(self.t.deleted_at == None).get_sql(),  # noqa: E711
        )

    def test_ne_none_renders_is_not_null(self):
        self.assertEqual(
            'SELECT * FROM "users" WHERE "deleted_at" IS NOT NULL',
            Query.from_(self.t).select("*").where(self.t.deleted_at != None).get_sql(),  # noqa: E711
        )

    def test_explicit_isnull_still_works(self):
        self.assertEqual(
            'SELECT * FROM "users" WHERE "deleted_at" IS NULL',
            Query.from_(self.t).select("*").where(self.t.deleted_at.isnull()).get_sql(),
        )

    def test_eq_none_in_a_join_criterion(self):
        other = Table("profiles")
        q = Query.from_(self.t).join(other).on(self.t.id == other.user_id).select("*").where(other.bio == None)  # noqa: E711
        self.assertIn('"bio" IS NULL', q.get_sql())

    def test_eq_none_inside_an_or_expression(self):
        q = (
            Query.from_(self.t)
            .select("*")
            .where((self.t.deleted_at == None) | (self.t.name == "x"))  # noqa: E711
        )
        self.assertIn('"deleted_at" IS NULL', q.get_sql())
        self.assertNotIn("=null", q.get_sql())

    def test_non_null_comparisons_are_untouched(self):
        self.assertEqual(
            'SELECT * FROM "users" WHERE "id"=1',
            Query.from_(self.t).select("*").where(self.t.id == 1).get_sql(),
        )

    def test_isin_with_none_is_rejected(self):
        with self.assertRaises(AmbiguousNullCriterionError):
            Query.from_(self.t).select("*").where(self.t.id.isin([1, None])).get_sql()

    def test_notin_with_none_is_rejected(self):
        with self.assertRaises(AmbiguousNullCriterionError):
            Query.from_(self.t).select("*").where(self.t.id.notin([1, None])).get_sql()

    def test_isin_with_only_none_is_rejected(self):
        with self.assertRaises(AmbiguousNullCriterionError):
            Query.from_(self.t).select("*").where(self.t.id.isin([None])).get_sql()

    def test_isin_with_subquery_is_not_inspected(self):
        sub = Query.from_(Table("other")).select("id")
        sql = Query.from_(self.t).select("*").where(self.t.id.isin(sub)).get_sql()
        self.assertIn("IN (SELECT", sql)


class ParameterValueTests(TestCase):
    """Bound parameters must carry Python values, not pre-rendered SQL fragments."""

    t = Table("users")

    def _param(self, value, parameter=None):
        parameter = parameter or QmarkParameter()
        Query.from_(self.t).select("*").where(self.t.c == value).get_sql(parameter=parameter)
        return parameter.get_parameters()

    def test_string_is_not_quoted(self):
        self.assertEqual(["foobar"], self._param("foobar"))

    def test_string_with_quote_is_not_escaped_twice(self):
        self.assertEqual(["a'b"], self._param("a'b"))

    def test_string_with_backslash_is_untouched(self):
        self.assertEqual(["a\\"], self._param("a\\"))

    def test_integers_and_floats_stay_numeric(self):
        self.assertEqual([7], self._param(7))
        self.assertEqual([2.5], self._param(2.5))

    def test_decimal_stays_decimal(self):
        value = decimal.Decimal("3.14")
        self.assertIs(value, self._param(value)[0])

    def test_datetime_stays_datetime(self):
        value = datetime.datetime(2026, 1, 2, 3, 4, 5)
        self.assertIs(value, self._param(value)[0])

    def test_date_stays_date(self):
        value = datetime.date(2026, 1, 2)
        self.assertIs(value, self._param(value)[0])

    def test_uuid_stays_uuid(self):
        value = uuid.UUID(int=7)
        self.assertIs(value, self._param(value)[0])

    def test_bytes_stay_bytes(self):
        value = b"abc"
        self.assertIs(value, self._param(value)[0])

    def test_bool_stays_bool(self):
        self.assertIs(True, self._param(True)[0])
        self.assertIs(False, self._param(False)[0])

    def test_enum_is_unwrapped_to_its_value(self):
        class Color(str):
            pass

        self.assertEqual(["red"], self._param(Color("red")))

    def test_named_parameter_maps_are_still_populated(self):
        parameter = NamedParameter()
        self._param("x", parameter)
        self.assertEqual({"param1": "x"}, parameter.get_parameters())

    def test_pyformat_parameter_maps_are_still_populated(self):
        parameter = PyformatParameter()
        self._param("x", parameter)
        self.assertEqual({"param1": "x"}, parameter.get_parameters())

    def test_format_parameter_is_positional(self):
        parameter = FormatParameter()
        self._param("x", parameter)
        self.assertEqual(["x"], parameter.get_parameters())

    def test_driver_roundtrip_preserves_date_type(self):
        # The real failure mode: a stringified date breaks comparisons against a DATE column.
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE t(d DATE)")
        conn.execute("INSERT INTO t VALUES('2024-02-22')")
        parameter = QmarkParameter()
        q = Query.from_(Table("t")).select("*").where(Table("t").d == datetime.date(2024, 2, 22))
        sql = q.get_sql(parameter=parameter)
        rows = conn.execute(sql, parameter.get_parameters()).fetchall()
        conn.close()
        self.assertEqual(1, len(rows))


class LikeEscapeTests(TestCase):
    def test_escape_like_pattern(self):
        self.assertEqual("100\\%\\_off", escape_like_pattern("100%_off"))

    def test_escape_char_itself_is_doubled(self):
        self.assertEqual("a\\\\b", escape_like_pattern("a\\b"))

    def test_custom_escape_char(self):
        self.assertEqual("a!%b", escape_like_pattern("a%b", escape_char="!"))

    def test_escape_clause_ansi(self):
        self.assertEqual("ESCAPE '\\'", like_escape_clause(dialect=Dialects.POSTGRESQL))

    def test_escape_clause_mysql(self):
        self.assertEqual("ESCAPE '\\\\'", like_escape_clause(dialect=Dialects.MYSQL))

    def test_like_literal_ansi(self):
        sql = Query.from_(Table("u")).select("*").where(Table("u").n.like_literal("100%_off")).get_sql()
        self.assertEqual(
            "SELECT * FROM \"u\" WHERE \"n\" LIKE '100\\%\\_off' ESCAPE '\\'",
            sql,
        )

    def test_like_literal_mysql(self):
        sql = MySQLQuery.from_(Table("u")).select("*").where(Table("u").n.like_literal("100%_off")).get_sql()
        self.assertEqual(
            "SELECT * FROM `u` WHERE `n` LIKE '100\\\\%\\\\_off' ESCAPE '\\\\'",
            sql,
        )

    def test_not_like_literal(self):
        sql = Query.from_(Table("u")).select("*").where(Table("u").n.not_like_literal("a_b")).get_sql()
        self.assertIn("NOT LIKE 'a\\_b' ESCAPE", sql)

    def test_invalid_escape_char_rejected(self):
        with self.assertRaises(ValueError):
            Table("u").n.like_literal("x", escape_char="ab")


class IdentifierAuditTests(TestCase):
    def test_clean_query_passes(self):
        t = Table("users")
        assert_safe_identifiers(Query.from_(t).select(t.id).where(t.name == "x"))

    def test_quoted_odd_identifier_is_safe(self):
        t = Table('u"; DROP TABLE x; --')
        assert_safe_identifiers(Query.from_(t).select("*"))

    def test_unquoted_odd_identifier_is_flagged(self):
        t = Table("a b")
        with self.assertRaises(UnsafeIdentifierError):
            assert_safe_identifiers(Query.from_(t).select("*"), quote_char=None)

    def test_unquoted_plain_identifier_passes(self):
        t = Table("users")
        assert_safe_identifiers(Query.from_(t).select(t.id), quote_char=None)

    def test_column_alias_is_checked(self):
        t = Table("users")
        q = Query.from_(t).select(t["a b"].as_("x y"))
        with self.assertRaises(UnsafeIdentifierError):
            assert_safe_identifiers(q, quote_char=None)

    def test_nul_in_identifier_always_flagged(self):
        t = Table("a\x00b")
        with self.assertRaises(UnsafeIdentifierError):
            assert_safe_identifiers(Query.from_(t).select("*"))

    def test_table_alias_is_checked(self):
        t = Table("users").as_("bad alias")
        with self.assertRaises(UnsafeIdentifierError):
            assert_safe_identifiers(Query.from_(t).select("*"), quote_char=None)


if __name__ == "__main__":
    unittest.main()
