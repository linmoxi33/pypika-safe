"""Dialect-aware literal and criterion safety helpers.

This module exists because PyPika's default value emission is *dialect-blind*: it
escapes a string literal by doubling the quote character, which is correct for
standard SQL but wrong for MySQL / ClickHouse, where a backslash also escapes the
following character.  The result is that a value such as ``x\\' OR 1=1 -- `` closes
the literal early and injects SQL.

Everything here is deliberately dependency-free so it can be imported from
``pypika.terms`` without creating an import cycle.

Public API
----------
``escape_string_literal``
    Render a Python ``str`` as a SQL string literal for a given dialect.
``escape_like_pattern``
    Escape ``%`` / ``_`` / the escape character inside a LIKE pattern.
``like_escape_clause``
    The ``ESCAPE '<char>'`` fragment, rendered correctly per dialect.
``assert_safe_identifiers``
    Audit a built query for identifiers that would be emitted unquoted and unsafe.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pypika.enums import Dialects

__all__ = [
    "AmbiguousNullCriterionError",
    "UnsafeIdentifierError",
    "UnsafeLiteralError",
    "BACKSLASH_ESCAPE_DIALECTS",
    "assert_safe_identifiers",
    "escape_like_pattern",
    "escape_string_literal",
    "is_plain_identifier",
    "like_escape_clause",
    "uses_backslash_escapes",
]


class UnsafeLiteralError(ValueError):
    """Raised when a value cannot be rendered as a SQL literal without ambiguity."""


class UnsafeIdentifierError(ValueError):
    """Raised when an identifier would be emitted in a way that can break out of its context."""


class AmbiguousNullCriterionError(ValueError):
    """Raised when ``IN`` / ``NOT IN`` receives ``None``, which never matches in SQL."""


#: Dialects in which a backslash escapes the next character inside a string literal.
#:
#: MySQL: enabled unless ``NO_BACKSLASH_ESCAPES`` is set on the session.
#: ClickHouse: backslash escapes are part of the literal grammar.
BACKSLASH_ESCAPE_DIALECTS = frozenset({Dialects.MYSQL, Dialects.CLICKHOUSE})

_BACKSLASH_ESCAPE_MAP = {
    "\\": "\\\\",
    "\0": "\\0",
    "\n": "\\n",
    "\r": "\\r",
    "\x1a": "\\Z",
    "\b": "\\b",
    "\t": "\\t",
}

_PLAIN_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


def _normalize_dialect(dialect: Any) -> Dialects | None:
    if dialect is None:
        return None
    if isinstance(dialect, Dialects):
        return dialect
    if isinstance(dialect, Enum):
        dialect = dialect.value
    if isinstance(dialect, str):
        for member in Dialects:
            if member.value == dialect.lower():
                return member
    return None


def uses_backslash_escapes(dialect: Any) -> bool:
    """Return ``True`` when *dialect* treats ``\\`` as an escape inside string literals."""
    return _normalize_dialect(dialect) in BACKSLASH_ESCAPE_DIALECTS


def escape_string_literal(
    value: str,
    quote_char: str = "'",
    dialect: Any = None,
    backslash_escapes: bool | None = None,
) -> str:
    """Render *value* as a quoted SQL string literal that is safe for *dialect*.

    The returned text includes the surrounding quotes.

    Standard SQL (PostgreSQL, SQLite, Oracle, MSSQL, Snowflake, Vertica, Redshift)
    escapes an embedded quote by doubling it and treats a backslash as an ordinary
    character.  MySQL and ClickHouse additionally treat a backslash as an escape
    introducer, so a trailing backslash before the closing quote would swallow that
    quote; there the backslash itself must be escaped first.

    ``backslash_escapes`` overrides the dialect inference.  Set it to ``False`` for a
    MySQL session running with ``NO_BACKSLASH_ESCAPES``, where doubling a backslash
    would change the stored value.

    A NUL byte cannot be represented in a standard SQL text literal (PostgreSQL
    rejects it outright), so it raises :class:`UnsafeLiteralError` instead of being
    silently dropped or smuggled through.
    """
    if not isinstance(value, str):
        raise TypeError(f"escape_string_literal expects str, got {type(value).__name__}")
    if not quote_char:
        raise ValueError("escape_string_literal requires a quote_char")

    use_backslash = uses_backslash_escapes(dialect) if backslash_escapes is None else bool(backslash_escapes)

    if use_backslash:
        # Backslash is an escape introducer here, so it has to be neutralised before
        # anything else; the quote itself is doubled (valid in both sql_modes) rather
        # than backslash-escaped, so the literal stays parseable even when the session
        # runs with NO_BACKSLASH_ESCAPES.
        out = []
        for ch in value:
            if ch == "\\" or ch in _BACKSLASH_ESCAPE_MAP:
                out.append(_BACKSLASH_ESCAPE_MAP[ch])
            elif ch == quote_char:
                out.append(quote_char * 2)
            else:
                out.append(ch)
        return f"{quote_char}{''.join(out)}{quote_char}"

    if "\0" in value:
        raise UnsafeLiteralError(
            "NUL byte (\\x00) cannot be represented in a standard SQL string literal. "
            "Strip or reject it before building the query, or bind the value as a "
            "driver parameter instead."
        )

    return f"{quote_char}{value.replace(quote_char, quote_char * 2)}{quote_char}"


def escape_like_pattern(value: str, escape_char: str = "\\") -> str:
    """Escape LIKE metacharacters in *value* so it matches literally.

    ``%`` and ``_`` become ``\\%`` and ``\\_`` and the escape character itself is
    doubled.  Pair the result with :func:`like_escape_clause`.
    """
    if not escape_char or len(escape_char) != 1:
        raise ValueError("escape_char must be exactly one character")
    escaped = value.replace(escape_char, escape_char * 2)
    escaped = escaped.replace("%", escape_char + "%").replace("_", escape_char + "_")
    return escaped


def like_escape_clause(escape_char: str = "\\", dialect: Any = None) -> str:
    """Return the ``ESCAPE '<char>'`` fragment for *dialect*.

    MySQL / ClickHouse need the backslash doubled inside the literal, everyone else
    needs it raw.
    """
    return "ESCAPE " + escape_string_literal(escape_char, quote_char="'", dialect=dialect)


def is_plain_identifier(name: str) -> bool:
    """``True`` when *name* is safe to emit without any quoting at all."""
    return bool(_PLAIN_IDENTIFIER_RE.match(name))


def _walk(node: Any, seen: set[int]):
    """Yield *node* and everything reachable from it through instance state.

    ``QueryBuilder.nodes_`` only yields the builder itself (it does not descend into
    ``_from`` / ``_selects`` / ...), and ``Table.__getattr__`` manufactures a ``Field``
    for any unknown attribute, so the audit reads ``__dict__`` directly instead of
    probing attributes.
    """
    if node is None or isinstance(node, (str, bytes, int, float, bool)):
        return
    if isinstance(node, (list, tuple, set, frozenset)):
        for item in node:
            yield from _walk(item, seen)
        return
    if id(node) in seen:
        return
    seen.add(id(node))
    yield node

    state = getattr(node, "__dict__", None)
    if isinstance(state, dict):
        for child in state.values():
            yield from _walk(child, seen)


def _iter_identifier_names(query: Any):
    from pypika.queries import Schema, Table
    from pypika.terms import Field, Star

    for node in _walk(query, set()):
        if isinstance(node, Star):
            continue
        if isinstance(node, Table):
            name = getattr(node, "_table_name", None)
            if isinstance(name, str):
                yield "table", name
            alias = getattr(node, "alias", None)
            if isinstance(alias, str):
                yield "table alias", alias
        elif isinstance(node, Schema):
            name = getattr(node, "_name", None)
            if isinstance(name, str):
                yield "schema", name
        elif isinstance(node, Field):
            name = getattr(node, "name", None)
            if isinstance(name, str) and name != "*":
                yield "column", name
            alias = getattr(node, "alias", None)
            if isinstance(alias, str):
                yield "column alias", alias


def assert_safe_identifiers(query: Any, quote_char: str | None = '"') -> None:
    """Raise :class:`UnsafeIdentifierError` if *query* has identifiers that leak.

    Quoted identifiers are safe for any content because the quote character is
    doubled, so this audit only fires when identifiers are emitted *unquoted*
    (``get_sql(quote_char=None)``) and the name is not a plain identifier, or when a
    name contains a NUL byte, which no SQL driver can carry.
    """
    problems: list[str] = []
    for kind, name in _iter_identifier_names(query):
        if "\0" in name:
            problems.append(f"{kind} {name!r} contains a NUL byte")
        elif not quote_char and not is_plain_identifier(name):
            problems.append(f"{kind} {name!r} would be emitted unquoted but is not a plain identifier")
    if problems:
        raise UnsafeIdentifierError(
            "unsafe identifier(s) in query: " + "; ".join(problems) + ". Quote identifiers or rename them."
        )
