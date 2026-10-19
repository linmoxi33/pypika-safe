# Changelog

## pypika-safe 0.51.1.post1 (2026-10-19)

Fork of PyPika 0.51.1. Same public API; the value-emission layer is fixed.
Full detail in [README.md](README.md) and [NOTICE](NOTICE).

### Security

- **MySQL / ClickHouse literal escaping.** String literals are now escaped with
  knowledge of the dialect. A backslash is doubled in backslash-escape dialects, so
  a value such as `x\' OR 1=1 -- ` can no longer terminate the literal and inject
  SQL (upstream issues #844, #238). ANSI dialects are unchanged.
- **Control characters.** `\n`, `\r`, `\t`, `\b`, `\Z` and `\0` are named rather than
  embedded raw in backslash-escape dialects.
- **NUL bytes.** Rejected with `UnsafeLiteralError` where the engine cannot represent
  them (PostgreSQL, standard SQL) instead of being silently dropped.
- **`bytes` values.** Rejected instead of leaking `repr()` into the SQL text.
- **Identifier audit.** New `assert_safe_identifiers()` flags identifiers that would
  be emitted unquoted and unsafe.

### Fixed

- `field == None` / `field != None` now render `IS NULL` / `IS NOT NULL`. The old
  `= null` form is valid SQL that matches nothing, so the filter silently returned
  zero rows.
- `IN` / `NOT IN` with a `None` member raises `AmbiguousNullCriterionError` instead of
  emitting a predicate that can never be true.
- Empty `isin([])` / `notin([])` render `1=0` / `1=1` instead of `IN ()`, which is a
  syntax error on PostgreSQL, Oracle, MSSQL and DuckDB.
- Bound parameters now carry Python values instead of pre-rendered SQL fragments.
  Strings are no longer pre-quoted, and `date`, `datetime`, `Decimal`, `UUID` and
  `bytes` keep their type so drivers can bind them correctly.

### Added

- `pypika.safety`: `escape_string_literal`, `escape_like_pattern`,
  `like_escape_clause`, `assert_safe_identifiers`, `is_plain_identifier`.
- `Field.like_literal()` / `Field.not_like_literal()` and `LikeCriterion` for
  matching user input literally, with the matching `ESCAPE` clause.
- `QueryBuilder.BACKSLASH_ESCAPES` (and a `backslash_escapes=` kwarg on `get_sql`)
  for MySQL sessions running with `NO_BACKSLASH_ESCAPES`.
- `pypika/tests/test_safety.py`: 76 tests, including real-SQLite execution assertions.
- `tools/upstream_compare.py`, `tools/verify_mysql_literals.py`,
  `tools/verify_strict_engine.py`.

### Changed

- Distribution name is `pypika-safe`; the import package is still `pypika`.
- Two upstream parameter tests updated: they expected stringified dates, the corrected
  behaviour passes `datetime.date`.

### Compatibility

- 1099 upstream tests pass unchanged. Three behaviour changes are intentional and
  documented in README's migration table.

---

## v0.51.1 (2026-02-04)

Upstream release. See the upstream repository for its history; entries below are
unchanged from `kayak/pypika`.

## v0.50.0 (2025-01-14)

### New Features

- **JQL (Jira Query Language) support** - New `JiraQuery` class for building Jira queries with `isempty()` and `notempty()` methods (#721)
- **QUALIFY clause** - Filter rows based on window function results (#841)
- **Bitwise OR support** - New `bitwiseor()` method on fields (#825)
- **ClickHouse DISTINCT ON** - `distinct_on()` method for ClickHouse queries (#817)
- **ClickHouse LIMIT BY** - `limit_by()` and `limit_offset_by()` methods (#817)
- **ClickHouse FINAL** - `final()` method for FINAL keyword (#765)
- **ClickHouse SAMPLE** - `sample()` method for approximate query processing (#707)
- **Oracle LIMIT/OFFSET** - `limit()` and `offset()` support using FETCH NEXT/OFFSET ROWS syntax (#754)
- **CREATE/DROP INDEX** - `Query.create_index()` and `Query.drop_index()` with support for unique, partial, and conditional indices (#753)
- **Pipe operator** - `QueryBuilder.pipe()` method for functional composition (#759)
- **Improved parameterized queries** - `get_parameters()` method to collect parameter values, `ListParameter` and `DictParameter` base classes (#794)
- **Auto increment columns** - Auto increment support on SqlTypes for CREATE TABLE (#829)
- **datetime.time support** - Proper handling of `datetime.time` values (#837)

### Bug Fixes

- Fixed `EmptyCriterion` handling in `&`, `|`, `^` operations with `Criterion` (#732)
- Fixed `Field.__init__` to accept string table names (#742)
- Fixed `isin()` and `notin()` to accept `frozenset` (#744)
- Fixed MySQL set operations (UNION/INTERSECT/MINUS) to wrap queries in parentheses (#782)
- Fixed PostgreSQL array syntax for UPDATE statements (#644)
- Fixed escape quotes in identifiers (#811)

### Typing & Compatibility

- Added `py.typed` marker for PEP 561 compliance (#666)
- Fixed typing hint for `@builder` decorator to preserve callable type (#740)
- Fixed types for mypy downstream usage, added `__all__` exports (#815)
- Improved typing for builder methods (#850)
- Added Python 3.13 and 3.14 support (#848, #851)
- Applied future type style annotations (#853)

### Documentation

- Added comprehensive documentation for all new features to README.rst
- Added documentation for: Analytic Queries (NTILE, RANK, FIRST_VALUE, LAST_VALUE, MEDIAN, AVG, STDDEV), Window Frames, ROLLUP, Pseudo Columns, TEMPORARY/UNLOGGED tables
- Unified documentation between README.rst and ReadTheDocs (single source of truth)
- Fixed PseudoColumn import in docs (#698)
- Added contributing guidelines (#758)
- Various typo fixes (#695, #801, #804)

### Internal

- Refactored `Interval` to inherit from `Term` (#838)
- Refactored shared logic for `Criterion` comparisons (#849)
- Updated CI to test Python 3.8-3.14 and PyPy 3.9-3.11 on Ubuntu and macOS
- Added GitHub Actions release workflow for PyPI publishing
- Removed tox dependency, simplified test running
- Updated Sphinx and other dev dependencies
