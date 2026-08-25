from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from pr_reviewer.config import get_settings

QueryParams = Sequence[Any] | dict[str, Any] | None
Row = dict[str, Any]

_pool: ConnectionPool[Connection[Row]] | None = None


def get_pool() -> ConnectionPool[Connection[Row]]:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            get_settings().database_url,
            kwargs={"row_factory": dict_row},
            min_size=1,
            max_size=10,
            open=True,
            timeout=10,
        )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def connection() -> Iterator[Connection[Row]]:
    with get_pool().connection() as conn:
        yield conn


def fetch_one(sql: str, params: QueryParams = None) -> Row | None:
    with connection() as conn:
        cursor = conn.execute(sql, params)
        row = cursor.fetchone()
        return dict(row) if row is not None else None


def fetch_all(sql: str, params: QueryParams = None) -> list[Row]:
    with connection() as conn:
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def execute(sql: str, params: QueryParams = None) -> int:
    with connection() as conn:
        cursor = conn.execute(sql, params)
        return cursor.rowcount
