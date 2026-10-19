# Release v0.51.1.post1 — dialect-aware literal escaping

> Fork of [kayak/pypika](https://github.com/kayak/pypika) at 0.51.1 (Apache-2.0).
> Import package is still `pypika`; distribution name is `pypika-safe`.

## Why this release exists

PyPika escapes every string literal the same way for every database: it doubles the quote character. On MySQL and ClickHouse a backslash also escapes the next character, so the escaping is wrong in a way that lets a value break out of its literal.

Reproduced against upstream 0.51.1 before any change:

```python
payload = "x\\' OR 1=1 -- "
MySQLQuery.from_(users).select(users.star).where(users.name == payload).get_sql()
# upstream : SELECT * FROM `users` WHERE `name`='x\'' OR 1=1 -- '   -> every row
# this fork: SELECT * FROM `users` WHERE `name`='x\\'' OR 1=1 -- '  -> the literal only
```

Tracked upstream as [#844](https://github.com/kayak/pypika/issues/844) (open) and [#238](https://github.com/kayak/pypika/issues/238) (open since 2019). The project is in slow maintenance ([#737](https://github.com/kayak/pypika/issues/737)).

## Highlights

### Security

- **Dialect-aware string escaping.** Backslash doubled on MySQL / ClickHouse; ANSI dialects byte-identical to before. Control characters named (`\n`, `\r`, `\t`, `\b`, `\Z`, `\0`); NUL rejected where the engine cannot store it.
- **`bytes` rejected** instead of leaking `repr()` into the SQL text.
- **`assert_safe_identifiers()`** to audit queries for identifiers that leak when emitted unquoted.

### Correctness

- `field == None` → `IS NULL`; `field != None` → `IS NOT NULL`. The old `= null` matched zero rows.
- `IN` / `NOT IN` with a `None` member raises instead of emitting a predicate that is never true.
- Empty `isin([])` / `notin([])` → `1=0` / `1=1`, portable; `IN ()` is a syntax error on PostgreSQL / Oracle / MSSQL / DuckDB.
- **Bound parameters carry Python values.** No more `"'foobar'"`; `date`, `datetime`, `Decimal`, `UUID`, `bytes` keep their type.

### Added

- `Field.like_literal()` / `not_like_literal()` with the matching `ESCAPE` clause.
- `QueryBuilder.BACKSLASH_ESCAPES` for MySQL sessions with `NO_BACKSLASH_ESCAPES`.
- `pypika.safety` module: `escape_string_literal`, `escape_like_pattern`, `like_escape_clause`, `assert_safe_identifiers`, `is_plain_identifier`.
- Three verification scripts under `tools/`.

## Verification

| Check | Upstream 0.51.1 | This fork |
|---|---|---|
| `pytest pypika/tests` | 1099 passed | **1175 passed**, 117 subtests |
| `tools/upstream_compare.py` (15 properties) | 3 passed / 12 failed | **15 passed / 0 failed** |
| `tools/verify_mysql_literals.py` (13 payloads) | 9/13 round-trip | **13/13 round-trip** |
| `tools/verify_strict_engine.py` (DuckDB) | `IN ()` → parser error; `=null` → 0 rows | **PASS** |

Reproduce:

```bash
pip install -r requirements-dev.txt
python -m pytest pypika/tests -q
python tools/upstream_compare.py .
python tools/verify_mysql_literals.py
python tools/verify_strict_engine.py
```

Known limitation: no MySQL / PostgreSQL / ClickHouse server was available in the build environment, so dialect behaviour is verified by MySQL-grammar round-trip and strict-engine execution, not against a live server.

## Compatibility

Public API unchanged. Intentional behaviour changes (migration table in the README):

| Change | Old behaviour if you need it |
|---|---|
| `== None` → `IS NULL` | `Field("x").eq(NullValue())` |
| `isin([...None])` raises | filter `None` out, or `x.isin(vals) \| x.isnull()` |
| `isin([])` → `1=0` | — |
| parameters carry Python values | remove any quote-stripping workaround |
| `bytes` raises | decode explicitly, or bind as a parameter |

Two upstream tests updated (`test_param_select_join`, `test_param_select_subquery`) because they asserted stringified dates. Rendered SQL is identical; only the driver-facing value changed. No test was deleted, skipped or weakened.

## Install

```bash
pip install -e .
```

Python 3.9+. Only runtime dependency is `typing_extensions` on Python < 3.11 — unchanged from upstream.

## License

Apache License 2.0, inherited. `LICENSE.txt` is byte-identical to upstream. `NOTICE` records the original copyright (Kayak.com, Timothy Heys), the fork copyright, and the full list of modified files per section 4.

Not affiliated with or endorsed by Kayak.com. Bugs in this fork are this fork's responsibility — report them here.
