"""Verify MySQL literal rendering by parsing it back with a real MySQL grammar.

No MySQL server is available on this machine, so the check is done with sqlglot's
MySQL grammar: every generated literal is parsed back and the recovered string
must be byte-identical to the Python value.  If the escaping were wrong, the parser
would either fail (unterminated literal) or recover a truncated value (injection).

A structural check on the parse tree additionally proves the payload did not become
a new clause: no extra OR / DROP / SELECT nodes may appear.
"""

from __future__ import annotations

import sys

import sqlglot
from sqlglot import exp

from pypika import MySQLQuery, Table

T = Table("users")

PAYLOADS = [
    "O'Brien",
    "a\\",
    "x\\' OR 1=1 -- ",
    "\\'; DROP TABLE users; --",
    "'; SELECT * FROM secrets; --",
    'a"b',
    "line1\nline2",
    "a\tb",
    "a\x1ab",
    "back\\\\slash",
    "名字 'quoted'",
    "100%_off",
    "",
]


def main() -> int:
    failures = 0
    print(f"{'payload':<34}{'parsed literal':<34}{'status'}")
    print("-" * 84)
    for payload in PAYLOADS:
        sql = MySQLQuery.from_(T).select(T.star).where(T.name == payload).get_sql()
        try:
            tree = sqlglot.parse_one(sql, dialect="mysql")
        except Exception as exc:  # noqa: BLE001
            print(f"{payload!r:<34}{'':<34}PARSE-ERROR {type(exc).__name__}")
            failures += 1
            continue

        literals = [node.this for node in tree.find_all(exp.Literal) if node.is_string]
        recovered = literals[0] if literals else None

        extra_or = len(list(tree.find_all(exp.Or)))
        extra_drop = len(list(tree.find_all(exp.Drop)))
        extra_select = len(list(tree.find_all(exp.Select)))

        problems = []
        if recovered != payload:
            problems.append(f"value mismatch (got {recovered!r})")
        if extra_or:
            problems.append(f"{extra_or} extra OR")
        if extra_drop:
            problems.append(f"{extra_drop} extra DROP")
        if extra_select != 1:
            problems.append(f"{extra_select} SELECT nodes")

        status = "OK" if not problems else "FAIL: " + ", ".join(problems)
        if problems:
            failures += 1
        shown = (recovered if recovered is not None else "")[:32]
        print(f"{payload!r:<34}{shown!r:<34}{status}")

    print("-" * 84)
    total = len(PAYLOADS)
    print(f"{total - failures}/{total} payloads round-tripped cleanly")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
