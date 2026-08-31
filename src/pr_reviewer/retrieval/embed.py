"""Embedding provider contract and the v1 1536-dimension check.

Model name and dimensions live on the generation, not on each chunk, so mixing
models or widths in one generation cannot be represented. The schema pins
vector(1536); this module fails closed if the live column drifts.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from psycopg import Connection

V1_EMBEDDING_DIMENSIONS = 1536
_VECTOR_TYPE = f"vector({V1_EMBEDDING_DIMENSIONS})"


class EmbeddingContractError(RuntimeError):
    """The local schema is not the v1 1536-dimension embedding contract."""


class EmbeddingDimensionError(ValueError):
    """An embedder advertised or returned a width other than 1536."""


class EmbeddingProvider(Protocol):
    model_name: str
    dimensions: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def assert_v1_embedding_contract(conn: Connection[Any]) -> None:
    row = conn.execute(
        """
        select format_type(a.atttypid, a.atttypmod) as typ
        from pg_attribute a
        join pg_class c on c.oid = a.attrelid
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public'
          and c.relname = 'code_chunks'
          and a.attname = 'embedding'
          and a.attnum > 0
          and not a.attisdropped
        """
    ).fetchone()
    typ = _value(row, "typ", 0) if row is not None else None
    if typ != _VECTOR_TYPE:
        raise EmbeddingContractError(f"code_chunks.embedding must be {_VECTOR_TYPE}, found {typ!r}")

    checks = conn.execute(
        """
        select pg_get_constraintdef(oid) as definition
        from pg_constraint
        where conrelid = 'embedding_generations'::regclass and contype = 'c'
        """
    ).fetchall()
    definitions = " ".join(str(_value(item, "definition", 0)) for item in checks)
    if "1536" not in definitions:
        raise EmbeddingContractError("embedding_generations.dimensions must be constrained to 1536")


def embed_texts(provider: EmbeddingProvider, texts: Sequence[str]) -> list[list[float]]:
    if provider.dimensions != V1_EMBEDDING_DIMENSIONS:
        raise EmbeddingDimensionError(
            f"embedder {provider.model_name!r} has dimensions "
            f"{provider.dimensions}, v1 requires {V1_EMBEDDING_DIMENSIONS}"
        )
    if not texts:
        return []
    vectors = provider.embed(texts)
    if len(vectors) != len(texts):
        raise EmbeddingDimensionError("embedder returned the wrong number of vectors")
    for vector in vectors:
        if len(vector) != V1_EMBEDDING_DIMENSIONS:
            raise EmbeddingDimensionError(
                f"embedder {provider.model_name!r} returned {len(vector)} dimensions, "
                f"v1 requires {V1_EMBEDDING_DIMENSIONS}"
            )
    return vectors


def _value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row[key]
    return row[index]
