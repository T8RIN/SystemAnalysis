from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg2
from pgvector.psycopg2 import register_vector
from psycopg2.extras import Json, RealDictCursor

from .config import AppConfig


@dataclass(frozen=True)
class Document:
    id: int
    content: str
    metadata: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class SearchResult(Document):
    distance: float
    score: float


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in values) + "]"


class RagRepository:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.conn: psycopg2.extensions.connection | None = None

    def connect(self) -> None:
        if self.conn is not None and not self.conn.closed:
            return
        self.conn = psycopg2.connect(
            dbname=self.config.db_name,
            user=self.config.db_user,
            password=self.config.db_password,
            host=self.config.db_host,
            port=self.config.db_port,
        )
        self.conn.autocommit = False

    def close(self) -> None:
        if self.conn is not None and not self.conn.closed:
            self.conn.close()

    def ensure_schema(self, dimension: int) -> None:
        if dimension < 1 or dimension > 4096:
            raise ValueError("Размерность вектора должна быть от 1 до 4096.")
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            conn.commit()
        except Exception as exc:
            conn.rollback()
            message = (
                "Не удалось включить расширение pgvector. "
                "Проверьте, что PostgreSQL запущен и расширение vector установлено."
            )
            raise RuntimeError(message) from exc

        register_vector(conn)
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS documents (
                    id SERIAL PRIMARY KEY,
                    content TEXT NOT NULL,
                    embedding vector({dimension}) NOT NULL,
                    metadata JSONB DEFAULT '{{}}'::jsonb,
                    created_at TIMESTAMP DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS documents_embedding_hnsw_idx
                ON documents USING hnsw (embedding vector_cosine_ops);
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS documents_metadata_gin_idx
                ON documents USING gin (metadata);
                """
            )
        conn.commit()

    def insert_document(self, content: str, embedding: list[float], metadata: dict[str, Any] | None) -> int:
        conn = self._conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO documents (content, embedding, metadata)
                VALUES (%s, %s::vector, %s)
                RETURNING id;
                """,
                (content, vector_literal(embedding), Json(metadata or {})),
            )
            document_id = int(cur.fetchone()[0])
        conn.commit()
        return document_id

    def update_document(
        self,
        document_id: int,
        content: str,
        embedding: list[float],
        metadata: dict[str, Any] | None,
    ) -> bool:
        conn = self._conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE documents
                SET content = %s, embedding = %s::vector, metadata = %s
                WHERE id = %s;
                """,
                (content, vector_literal(embedding), Json(metadata or {}), document_id),
            )
            updated = cur.rowcount > 0
        conn.commit()
        return updated

    def delete_document(self, document_id: int) -> bool:
        conn = self._conn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM documents WHERE id = %s;", (document_id,))
            deleted = cur.rowcount > 0
        conn.commit()
        return deleted

    def truncate(self) -> None:
        conn = self._conn()
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE documents RESTART IDENTITY;")
        conn.commit()

    def get_document(self, document_id: int) -> Document | None:
        conn = self._conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, content, COALESCE(metadata, '{}'::jsonb) AS metadata, created_at
                FROM documents
                WHERE id = %s;
                """,
                (document_id,),
            )
            row = cur.fetchone()
        return self._to_document(row) if row else None

    def list_documents(self, query: str | None = None, limit: int = 200) -> list[Document]:
        conn = self._conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if query and query.strip():
                pattern = f"%{query.strip()}%"
                cur.execute(
                    """
                    SELECT id, content, COALESCE(metadata, '{}'::jsonb) AS metadata, created_at
                    FROM documents
                    WHERE content ILIKE %s OR metadata::text ILIKE %s
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s;
                    """,
                    (pattern, pattern, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT id, content, COALESCE(metadata, '{}'::jsonb) AS metadata, created_at
                    FROM documents
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s;
                    """,
                    (limit,),
                )
            rows = cur.fetchall()
        return [self._to_document(row) for row in rows]

    def similarity_search(
        self,
        embedding: list[float],
        top_k: int,
        source: str | None = None,
    ) -> list[SearchResult]:
        conn = self._conn()
        vector_value = vector_literal(embedding)
        top_k = max(1, min(int(top_k), 50))
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if source:
                cur.execute(
                    """
                    SELECT
                        id,
                        content,
                        COALESCE(metadata, '{}'::jsonb) AS metadata,
                        created_at,
                        embedding <=> %s::vector AS distance
                    FROM documents
                    WHERE metadata->>'source' = %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s;
                    """,
                    (vector_value, source, vector_value, top_k),
                )
            else:
                cur.execute(
                    """
                    SELECT
                        id,
                        content,
                        COALESCE(metadata, '{}'::jsonb) AS metadata,
                        created_at,
                        embedding <=> %s::vector AS distance
                    FROM documents
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s;
                    """,
                    (vector_value, vector_value, top_k),
                )
            rows = cur.fetchall()
        return [self._to_search_result(row) for row in rows]

    def count_documents(self) -> int:
        conn = self._conn()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM documents;")
            return int(cur.fetchone()[0])

    def sources(self) -> list[str]:
        conn = self._conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT metadata->>'source' AS source
                FROM documents
                WHERE metadata ? 'source'
                ORDER BY source;
                """
            )
            rows = cur.fetchall()
        return [row[0] for row in rows if row[0]]

    def stats_by_source(self) -> list[dict[str, Any]]:
        conn = self._conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT COALESCE(metadata->>'source', 'unknown') AS source, COUNT(*) AS total
                FROM documents
                GROUP BY 1
                ORDER BY total DESC, source ASC;
                """
            )
            return list(cur.fetchall())

    def _conn(self) -> psycopg2.extensions.connection:
        if self.conn is None or self.conn.closed:
            self.connect()
        if self.conn is None:
            raise RuntimeError("Не удалось создать подключение к PostgreSQL.")
        return self.conn

    @staticmethod
    def _to_document(row: dict[str, Any]) -> Document:
        return Document(
            id=int(row["id"]),
            content=str(row["content"]),
            metadata=dict(row["metadata"] or {}),
            created_at=row["created_at"],
        )

    @staticmethod
    def _to_search_result(row: dict[str, Any]) -> SearchResult:
        distance = float(row["distance"])
        return SearchResult(
            id=int(row["id"]),
            content=str(row["content"]),
            metadata=dict(row["metadata"] or {}),
            created_at=row["created_at"],
            distance=distance,
            score=1.0 - distance,
        )
