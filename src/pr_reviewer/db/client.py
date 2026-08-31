from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg import Connection, sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from pr_reviewer.config import get_settings

QueryParams = Sequence[Any] | dict[str, Any] | None
Row = dict[str, Any]
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1"})

_pool: ConnectionPool[Connection[Row]] | None = None


def ensure_database_exists(database_url: str) -> None:
    parts = urlsplit(database_url)
    if parts.hostname not in _LOCAL_HOSTS:
        return
    dbname = parts.path.lstrip("/")
    if not dbname:
        return
    admin_url = urlunsplit((parts.scheme, parts.netloc, "/postgres", parts.query, parts.fragment))
    with psycopg.connect(admin_url, autocommit=True) as conn:
        exists = conn.execute(
            "select 1 from pg_database where datname = %s",
            (dbname,),
        ).fetchone()
        if exists is not None:
            return
        owner = parts.username or "pr_reviewer"
        conn.execute(
            sql.SQL("create database {} owner {}").format(
                sql.Identifier(dbname),
                sql.Identifier(owner),
            )
        )


def get_pool() -> ConnectionPool[Connection[Row]]:
    global _pool
    if _pool is None:
        database_url = get_settings().database_url
        ensure_database_exists(database_url)
        _pool = ConnectionPool(
            database_url,
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
