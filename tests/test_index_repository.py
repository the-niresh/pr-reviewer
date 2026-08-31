"""Failing tests for embedding generations and local pgvector indexing (master Task 12).

Generations store model name and dimensions. Mixed models or dimensions in one
generation are unrepresentable. Indexing builds a generation in 'building', then
flips it active in one step so a half-built index is never queryable. Imports of
new modules stay inside test bodies.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator, Sequence
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row

from pr_reviewer.config import database_name_for_root, default_database_url
from pr_reviewer.db.client import connection as hosted_connection

REPO = Path(__file__).resolve().parent.parent
MIGRATIONS = REPO / "src" / "pr_reviewer" / "local_store" / "postgres_migrations"
HOSTED_URL = os.environ.get("DATABASE_URL", default_database_url(REPO))
LOCAL_DB_NAME = f"{database_name_for_root(REPO)}_retrieval_test"
V1_DIM = 1536


class FakeEmbedder:
    model_name = "text-embedding-3-small"
    dimensions = V1_DIM

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [_vector_for(text) for text in texts]


class WrongDimensionEmbedder:
    model_name = "text-embedding-3-small"
    dimensions = 768

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        del texts
        return [[0.0] * 768]


def _vector_for(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = [((digest[index % len(digest)] / 255.0) - 0.5) for index in range(V1_DIM)]
    values[0] = float(len(text) % 97) / 97.0
    return values


def _vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def _retrieval_migration() -> Path:
    matches = sorted(MIGRATIONS.glob("*_retrieval_generations.sql"))
    assert matches, "local pgvector migration *_retrieval_generations.sql is missing"
    return matches[0]


@pytest.fixture(scope="module")
def retrieval_database_url() -> Iterator[str]:
    _retrieval_migration()
    base = HOSTED_URL.rsplit("/", 1)[0]
    url = f"{base}/{LOCAL_DB_NAME}"
    with psycopg.connect(HOSTED_URL, autocommit=True) as admin:
        admin.execute(
            "select pg_terminate_backend(pid) from pg_stat_activity "
            "where datname = %s and pid <> pg_backend_pid()",
            (LOCAL_DB_NAME,),
        )
        admin.execute(f"drop database if exists {LOCAL_DB_NAME}")
        admin.execute(f"create database {LOCAL_DB_NAME}")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute((MIGRATIONS / "0000_extensions.sql").read_text(encoding="utf-8"))
        conn.execute(_retrieval_migration().read_text(encoding="utf-8"))
    yield url
    with psycopg.connect(HOSTED_URL, autocommit=True) as admin:
        admin.execute(
            "select pg_terminate_backend(pid) from pg_stat_activity "
            "where datname = %s and pid <> pg_backend_pid()",
            (LOCAL_DB_NAME,),
        )
        admin.execute(f"drop database if exists {LOCAL_DB_NAME}")


@pytest.fixture
def retrieval_conn(retrieval_database_url: str) -> Iterator[psycopg.Connection[dict[str, object]]]:
    conn = psycopg.connect(retrieval_database_url, row_factory=dict_row)
    conn.execute("truncate code_chunks, embedding_generations restart identity cascade")
    conn.commit()
    try:
        yield conn
    finally:
        conn.close()


def test_retrieval_migration_exists_after_extensions_and_has_no_approximate_index() -> None:
    migration = _retrieval_migration()
    names = sorted(path.name for path in MIGRATIONS.glob("*.sql"))
    assert names[0] == "0000_extensions.sql"
    assert migration.name in names
    sql = migration.read_text(encoding="utf-8").lower()
    assert "embedding_generations" in sql
    assert "code_chunks" in sql
    assert "tsvector" in sql
    assert "using gin" in sql
    assert "hnsw" not in sql
    assert "ivfflat" not in sql
    assert "vector(1536)" in sql


def test_retrieval_tables_do_not_exist_on_the_hosted_schema() -> None:
    with hosted_connection() as conn:
        rows = conn.execute(
            """
            select table_name from information_schema.tables
            where table_schema = 'public'
              and table_name = any(%s)
            """,
            (["embedding_generations", "code_chunks"],),
        ).fetchall()
    present = sorted(str(row["table_name"]) for row in rows)
    assert present == []


def test_schema_and_startup_check_enforce_the_v1_1536_contract(
    retrieval_conn: psycopg.Connection[dict[str, object]],
) -> None:
    from pr_reviewer.retrieval.embed import EmbeddingContractError, assert_v1_embedding_contract

    row = retrieval_conn.execute(
        """
        select format_type(a.atttypid, a.atttypmod) as typ
        from pg_attribute a
        join pg_class c on c.oid = a.attrelid
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relname = 'code_chunks' and a.attname = 'embedding'
        """
    ).fetchone()
    assert row is not None
    assert str(row["typ"]) == "vector(1536)"
    assert_v1_embedding_contract(retrieval_conn)

    retrieval_conn.execute("alter table code_chunks alter column embedding type vector(3)")
    retrieval_conn.commit()
    try:
        with pytest.raises(EmbeddingContractError):
            assert_v1_embedding_contract(retrieval_conn)
    finally:
        retrieval_conn.execute("alter table code_chunks alter column embedding type vector(1536)")
        retrieval_conn.commit()


def test_mixed_models_and_dimensions_are_unrepresentable_in_one_generation(
    retrieval_conn: psycopg.Connection[dict[str, object]],
) -> None:
    columns = {
        str(row["column_name"])
        for row in retrieval_conn.execute(
            """
            select column_name from information_schema.columns
            where table_schema = 'public' and table_name = 'code_chunks'
            """
        ).fetchall()
    }
    assert "model_name" not in columns
    assert "dimensions" not in columns

    with pytest.raises(psycopg.Error):
        retrieval_conn.execute(
            """
            insert into embedding_generations (
              installation_id, repository_id, commit_sha, model_name, dimensions, state
            ) values (1, 2, 'abc', 'text-embedding-3-small', 768, 'building')
            """
        )
    retrieval_conn.rollback()

    generation = retrieval_conn.execute(
        """
        insert into embedding_generations (
          installation_id, repository_id, commit_sha, model_name, dimensions, state
        ) values (1, 2, 'abc', 'text-embedding-3-small', 1536, 'building')
        returning id
        """
    ).fetchone()
    assert generation is not None
    with pytest.raises(psycopg.Error):
        retrieval_conn.execute(
            """
            insert into code_chunks (
              generation_id, file_path, language, start_line, end_line,
              content, content_hash, identity, strategy, embedding
            ) values (
              %s, 'a.py', 'python', 1, 1, 'x', repeat('a', 64), 'a.py::x',
              'ast_python', '[1,2,3]'::vector
            )
            """,
            (generation["id"],),
        )
    retrieval_conn.rollback()


def test_wrong_dimension_embedder_is_rejected_before_insert(
    retrieval_conn: psycopg.Connection[dict[str, object]],
    tmp_path: Path,
) -> None:
    from pr_reviewer.retrieval.embed import EmbeddingDimensionError
    from pr_reviewer.retrieval.index_repository import index_repository

    (tmp_path / "a.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
    with pytest.raises(EmbeddingDimensionError):
        index_repository(
            retrieval_conn,
            root=tmp_path,
            installation_id=1,
            repository_id=2,
            commit_sha="a" * 40,
            embedder=WrongDimensionEmbedder(),
        )


def test_index_builds_then_flips_active_and_building_is_not_queryable(
    retrieval_conn: psycopg.Connection[dict[str, object]],
    tmp_path: Path,
) -> None:
    from pr_reviewer.retrieval.index_repository import (
        exact_nearest_chunks,
        index_repository,
        queryable_chunks,
    )

    first_root = tmp_path / "first"
    first_root.mkdir()
    (first_root / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    first = index_repository(
        retrieval_conn,
        root=first_root,
        installation_id=7,
        repository_id=9,
        commit_sha="b" * 40,
        embedder=FakeEmbedder(),
    )
    assert first.state == "active"
    assert first.model_name == "text-embedding-3-small"
    assert first.dimensions == V1_DIM
    first_ids = {chunk.identity for chunk in queryable_chunks(retrieval_conn, 7, 9)}
    assert any("alpha" in identity for identity in first_ids)

    retrieval_conn.execute(
        """
        insert into embedding_generations (
          installation_id, repository_id, commit_sha, model_name, dimensions, state
        ) values (7, 9, %s, 'text-embedding-3-small', 1536, 'building')
        """,
        ("c" * 40,),
    )
    retrieval_conn.commit()
    still_first = {chunk.identity for chunk in queryable_chunks(retrieval_conn, 7, 9)}
    assert still_first == first_ids

    second_root = tmp_path / "second"
    second_root.mkdir()
    (second_root / "b.py").write_text("def beta():\n    return 2\n", encoding="utf-8")
    second = index_repository(
        retrieval_conn,
        root=second_root,
        installation_id=7,
        repository_id=9,
        commit_sha="d" * 40,
        embedder=FakeEmbedder(),
    )
    assert second.state == "active"
    assert second.id != first.id
    queryable = queryable_chunks(retrieval_conn, 7, 9)
    identities = {chunk.identity for chunk in queryable}
    assert any("beta" in identity for identity in identities)
    assert not any("alpha" in identity for identity in identities)
    states = {
        str(row["state"])
        for row in retrieval_conn.execute(
            "select state from embedding_generations where installation_id = 7"
        ).fetchall()
    }
    assert states <= {"active", "building", "retired"}
    active_count = retrieval_conn.execute(
        """
        select count(*) as n from embedding_generations
        where installation_id = 7 and repository_id = 9 and state = 'active'
        """
    ).fetchone()
    assert active_count is not None
    active_n = active_count["n"]
    assert isinstance(active_n, int)
    assert active_n == 1

    hits = exact_nearest_chunks(
        retrieval_conn,
        installation_id=7,
        repository_id=9,
        query=_vector_for("def beta():\n    return 2\n"),
        limit=5,
    )
    assert hits
    assert all("alpha" not in chunk.identity for chunk in hits)

    with pytest.raises(psycopg.Error):
        retrieval_conn.execute(
            """
            insert into embedding_generations (
              installation_id, repository_id, commit_sha, model_name, dimensions, state
            ) values (7, 9, %s, 'text-embedding-3-small', 1536, 'active')
            """,
            ("e" * 40,),
        )
    retrieval_conn.rollback()


def test_tsvector_gin_exists_and_no_approximate_index_is_installed(
    retrieval_conn: psycopg.Connection[dict[str, object]],
) -> None:
    indexes = {
        str(row["indexname"]): str(row["indexdef"]).lower()
        for row in retrieval_conn.execute(
            """
            select indexname, indexdef from pg_indexes
            where schemaname = 'public' and tablename in ('code_chunks', 'embedding_generations')
            """
        ).fetchall()
    }
    gin = [definition for definition in indexes.values() if "using gin" in definition]
    assert gin
    joined = " ".join(indexes.values())
    assert "hnsw" not in joined
    assert "ivfflat" not in joined


def test_exact_vector_scan_latency_is_measured_before_adding_an_approximate_index(
    retrieval_conn: psycopg.Connection[dict[str, object]],
) -> None:
    import time

    from pr_reviewer.retrieval.index_repository import exact_nearest_chunks

    generation = retrieval_conn.execute(
        """
        insert into embedding_generations (
          installation_id, repository_id, commit_sha, model_name, dimensions, state
        ) values (3, 4, %s, 'text-embedding-3-small', 1536, 'active')
        returning id
        """,
        ("f" * 40,),
    ).fetchone()
    assert generation is not None
    rows = []
    for index in range(300):
        content = f"def item_{index}():\n    return {index}\n"
        vector = _vector_literal(_vector_for(content))
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        rows.append(
            (
                generation["id"],
                f"item_{index}.py",
                "python",
                1,
                2,
                content,
                digest,
                f"item_{index}.py::item_{index}",
                "ast_python",
                vector,
            )
        )
    with retrieval_conn.cursor() as cursor:
        cursor.executemany(
            """
            insert into code_chunks (
              generation_id, file_path, language, start_line, end_line,
              content, content_hash, identity, strategy, embedding
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
            """,
            rows,
        )
    retrieval_conn.commit()
    query = _vector_for("def item_0():\n    return 0\n")
    started = time.perf_counter()
    hits = exact_nearest_chunks(
        retrieval_conn,
        installation_id=3,
        repository_id=4,
        query=query,
        limit=10,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert hits
    assert elapsed_ms >= 0
    plan_rows = retrieval_conn.execute(
        """
        explain
        select c.id from code_chunks c
        join embedding_generations g on g.id = c.generation_id
        where g.state = 'active' and g.installation_id = 3 and g.repository_id = 4
        order by embedding <=> %s::vector
        limit 10
        """,
        (_vector_literal(query),),
    ).fetchall()
    plan = "\n".join(str(next(iter(row.values()))) for row in plan_rows).lower()
    assert "hnsw" not in plan
    assert "ivfflat" not in plan
    print(f"exact_vector_scan_ms={elapsed_ms:.3f} n=300")
