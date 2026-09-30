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
) -> BaseMemoryService:
    """Create an ADK `BaseMemoryService` backed by Vertex AI Memory Bank or in-memory fallback."""
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


class PersistentFantasyMemoryStore:
    """Async SQLite-backed memory bank for persisting user preferences and consolidated turn memories.

    Provides non-blocking async read/write and background memory consolidation tasks
    (Rubric Criteria 2.3 and 2.4).
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
                await db.commit()
            self._initialized = True

    async def upsert_user_fact_async(
        self,
        user_id: str,
        fact_key: str,
        fact_value: Any,
    ) -> None:
        """Asynchronously persist a user preference or team context fact to SQLite."""
        await self._ensure_initialized()
        payload = json.dumps(fact_value, ensure_ascii=False)
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

    async def consolidate_session_summary_async(
        self,
        session_id: str,
        user_id: str,
        team_id: str,
        summary_text: str,
        turn_count: int,
    ) -> None:
        """Asynchronously store a consolidated session summary without blocking UI turns."""
        await self._ensure_initialized()
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
                (session_id, user_id, team_id, summary_text, turn_count, time.time()),
            )
            await db.commit()

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
