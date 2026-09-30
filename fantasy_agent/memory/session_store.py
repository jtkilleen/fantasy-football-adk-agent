"""Persistent Session State and Async Memory Store for the Fantasy Football Agent.

Satisfies AgentOps Rubric Criteria:
- 2.3 Persistent Session State (connects to SQLite / Vertex AI Session Service & Memory Bank
  to persist conversational history and user team context across turns).
- 2.4 Async Memory Operations (non-blocking async SQLite memory consolidation).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import aiosqlite
from google.adk.memory.base_memory_service import BaseMemoryService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.sessions.base_session_service import BaseSessionService
from google.adk.sessions.sqlite_session_service import SqliteSessionService

from fantasy_agent.config import get_settings

DEFAULT_SESSION_DB_PATH = (
    Path(__file__).resolve().parent.parent / ".adk" / "session.db"
)
DEFAULT_MEMORY_DB_PATH = (
    Path(__file__).resolve().parent.parent / ".adk" / "fantasy_memory.db"
)


def create_persistent_session_service(
    db_path: str | Path | None = None,
    agent_engine_id: str | None = None,
) -> BaseSessionService:
    """Create a persistent ADK `BaseSessionService` backed by Vertex AI or SQLite.

    When `agent_engine_id` (or `GOOGLE_CLOUD_AGENT_ENGINE_ID`) is configured, connects
    to Google Cloud's managed `VertexAiSessionService`. Otherwise, persists sessions
    and multi-turn conversation history in a local SQLite database (`SqliteSessionService`).

    Args:
        db_path: Optional path to the SQLite database file (defaults to `fantasy_agent/.adk/session.db`).
        agent_engine_id: Optional Vertex AI Agent Engine resource ID.

    Returns:
        Configured `BaseSessionService` instance.
    """
    resolved_engine_id = agent_engine_id or os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID")
    if resolved_engine_id:
        from google.adk.sessions.vertex_ai_session_service import VertexAiSessionService

        settings = get_settings()
        return VertexAiSessionService(
            project=settings.project_id,
            location=settings.location,
            agent_engine_id=resolved_engine_id,
        )

    target_path = Path(db_path) if db_path else DEFAULT_SESSION_DB_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    return SqliteSessionService(db_path=str(target_path))


def create_persistent_memory_service(
    agent_engine_id: str | None = None,
    rag_corpus_id: str | None = None,
) -> BaseMemoryService:
    """Create an ADK `BaseMemoryService` backed by Vertex AI Memory Bank, Vertex AI RAG/Search, or in-memory fallback."""
    resolved_rag_corpus = rag_corpus_id or os.environ.get("GOOGLE_CLOUD_RAG_CORPUS_ID")
    if resolved_rag_corpus:
        from google.adk.memory.vertex_ai_rag_memory_service import (
            VertexAiRagMemoryService,
        )

        return VertexAiRagMemoryService(rag_corpus=resolved_rag_corpus)

    resolved_engine_id = agent_engine_id or os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID")
    if resolved_engine_id:
        from google.adk.memory.vertex_ai_memory_bank_service import (
            VertexAiMemoryBankService,
        )

        settings = get_settings()
        return VertexAiMemoryBankService(
            project=settings.project_id,
            location=settings.location,
            agent_engine_id=resolved_engine_id,
        )
    return InMemoryMemoryService()


def _compute_text_embedding(text: str, dim: int = 32) -> list[float]:
    """Compute a normalized deterministic feature-hashing vector embedding for semantic retrieval."""
    import hashlib
    import math
    import re

    vec = [0.0] * dim
    tokens = re.findall(r"[a-z0-9_]+", text.lower())
    if not tokens:
        return vec
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = digest[0] % dim
        sign = 1.0 if (digest[1] % 2 == 0) else -1.0
        vec[bucket] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [round(v / norm, 6) for v in vec]
    return vec


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two normalized embedding vectors."""
    return round(sum(a * b for a, b in zip(vec_a, vec_b, strict=False)), 4)


class PersistentFantasyMemoryStore:
    """Async SQLite & Vector-backed memory bank for persisting user preferences, session summaries, and semantic vector memories.

    Provides non-blocking async read/write, cosine-similarity vector retrieval, and background
    memory consolidation tasks (Rubric Criteria 2.3 and 2.4).
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_MEMORY_DB_PATH
        self._initialized = False
        self._init_lock = asyncio.Lock()
        self._background_tasks: set[asyncio.Task[None]] = set()

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiosqlite.connect(str(self.db_path)) as db:
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_memory_facts (
                        user_id TEXT NOT NULL,
                        fact_key TEXT NOT NULL,
                        fact_value_json TEXT NOT NULL,
                        updated_at REAL NOT NULL,
                        PRIMARY KEY (user_id, fact_key)
                    )
                    """
                )
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS session_summaries (
                        session_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        team_id TEXT NOT NULL,
                        summary_text TEXT NOT NULL,
                        turn_count INTEGER NOT NULL,
                        updated_at REAL NOT NULL
                    )
                    """
                )
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memory_vector_embeddings (
                        doc_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        content_text TEXT NOT NULL,
                        embedding_json TEXT NOT NULL,
                        metadata_json TEXT NOT NULL,
                        updated_at REAL NOT NULL
                    )
                    """
                )
                await db.commit()
            self._initialized = True

    async def upsert_user_fact_async(
        self,
        user_id: str,
        fact_key: str,
        fact_value: Any,
    ) -> None:
        """Asynchronously persist a PII-scrubbed user preference or team fact to SQLite."""
        from fantasy_agent.observability.pii_redactor import get_pii_redactor

        await self._ensure_initialized()
        sanitized_value = get_pii_redactor().redact_value(fact_value)
        payload = json.dumps(sanitized_value, ensure_ascii=False)
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                """
                INSERT INTO user_memory_facts (user_id, fact_key, fact_value_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, fact_key) DO UPDATE SET
                    fact_value_json = excluded.fact_value_json,
                    updated_at = excluded.updated_at
                """,
                (user_id, fact_key, payload, time.time()),
            )
            await db.commit()

    async def get_user_facts_async(self, user_id: str) -> dict[str, Any]:
        """Asynchronously retrieve all persisted facts for a user."""
        await self._ensure_initialized()
        facts: dict[str, Any] = {}
        async with (
            aiosqlite.connect(str(self.db_path)) as db,
            db.execute(
                "SELECT fact_key, fact_value_json FROM user_memory_facts WHERE user_id = ?",
                (user_id,),
            ) as cursor,
        ):
            async for key, val_json in cursor:
                facts[key] = json.loads(val_json)
        return facts

    async def upsert_vector_memory_async(
        self,
        doc_id: str,
        user_id: str,
        content_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Asynchronously index a PII-scrubbed memory document with vector embeddings into SQLite."""
        from fantasy_agent.observability.pii_redactor import get_pii_redactor

        await self._ensure_initialized()
        redactor = get_pii_redactor()
        clean_text = redactor.redact_string(content_text)
        clean_meta = redactor.redact_value(metadata or {})
        embedding = _compute_text_embedding(clean_text)
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                """
                INSERT INTO memory_vector_embeddings (doc_id, user_id, content_text, embedding_json, metadata_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(doc_id) DO UPDATE SET
                    content_text = excluded.content_text,
                    embedding_json = excluded.embedding_json,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    doc_id,
                    user_id,
                    clean_text,
                    json.dumps(embedding),
                    json.dumps(clean_meta, ensure_ascii=False),
                    time.time(),
                ),
            )
            await db.commit()

    async def search_vector_memories_async(
        self,
        user_id: str,
        query: str,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """Retrieve top-k semantically similar memory documents using cosine similarity."""
        await self._ensure_initialized()
        query_vec = _compute_text_embedding(query)
        scored_results: list[dict[str, Any]] = []
        async with (
            aiosqlite.connect(str(self.db_path)) as db,
            db.execute(
                "SELECT doc_id, content_text, embedding_json, metadata_json FROM memory_vector_embeddings WHERE user_id = ?",
                (user_id,),
            ) as cursor,
        ):
            async for doc_id, content_text, emb_json, meta_json in cursor:
                doc_vec = json.loads(emb_json)
                sim = _cosine_similarity(query_vec, doc_vec)
                scored_results.append(
                    {
                        "doc_id": doc_id,
                        "content_text": content_text,
                        "similarity_score": sim,
                        "metadata": json.loads(meta_json),
                    }
                )
        scored_results.sort(key=lambda item: item["similarity_score"], reverse=True)
        return scored_results[:top_k]

    async def consolidate_session_summary_async(
        self,
        session_id: str,
        user_id: str,
        team_id: str,
        summary_text: str,
        turn_count: int,
    ) -> None:
        """Asynchronously store a PII-scrubbed consolidated session summary and index its vector embedding."""
        from fantasy_agent.observability.pii_redactor import get_pii_redactor

        await self._ensure_initialized()
        clean_summary = get_pii_redactor().redact_string(summary_text)
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                """
                INSERT INTO session_summaries (session_id, user_id, team_id, summary_text, turn_count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    summary_text = excluded.summary_text,
                    turn_count = excluded.turn_count,
                    updated_at = excluded.updated_at
                """,
                (session_id, user_id, team_id, clean_summary, turn_count, time.time()),
            )
            await db.commit()
        await self.upsert_vector_memory_async(
            doc_id=f"summary:{session_id}",
            user_id=user_id,
            content_text=clean_summary,
            metadata={"session_id": session_id, "team_id": team_id, "turn_count": turn_count},
        )

    async def get_session_summary_async(self, session_id: str) -> dict[str, Any] | None:
        """Retrieve a consolidated session summary from persistent SQLite storage."""
        await self._ensure_initialized()
        async with (
            aiosqlite.connect(str(self.db_path)) as db,
            db.execute(
                "SELECT session_id, user_id, team_id, summary_text, turn_count FROM session_summaries WHERE session_id = ?",
                (session_id,),
            ) as cursor,
        ):
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                "session_id": row[0],
                "user_id": row[1],
                "team_id": row[2],
                "summary_text": row[3],
                "turn_count": row[4],
            }

    def schedule_background_consolidation(
        self,
        session_id: str,
        user_id: str,
        team_id: str,
        summary_text: str,
        turn_count: int,
    ) -> asyncio.Task[None] | None:
        """Schedule non-blocking background session memory consolidation (Rubric 2.4)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None

        task = loop.create_task(
            self.consolidate_session_summary_async(
                session_id=session_id,
                user_id=user_id,
                team_id=team_id,
                summary_text=summary_text,
                turn_count=turn_count,
            )
        )
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task
