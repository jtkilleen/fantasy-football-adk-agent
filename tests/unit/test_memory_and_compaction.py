"""Unit tests for Milestone 4: History Compaction and Persistent Session & Memory State."""

from __future__ import annotations

from pathlib import Path

import pytest
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from fantasy_agent.agent import app, build_fantasy_app
from fantasy_agent.memory import (
    PersistentFantasyMemoryStore,
    build_context_cache_config,
    build_events_compaction_config,
    compact_llm_request_history,
    create_persistent_session_service,
)


def test_adk_app_and_compaction_configs() -> None:
    """Verify Rubric 2.2: ADK App configures EventsCompactionConfig and ContextCacheConfig."""
    fantasy_app = build_fantasy_app()
    assert fantasy_app.name == "fantasy_agent"
    assert fantasy_app.events_compaction_config is not None
    assert fantasy_app.events_compaction_config.compaction_interval == 5
    assert fantasy_app.events_compaction_config.token_threshold == 8000
    assert fantasy_app.resumability_config is not None
    assert fantasy_app.resumability_config.is_resumable is True
    assert app.name == "fantasy_agent"

    compaction_cfg = build_events_compaction_config(compaction_interval=4, overlap_size=1)
    assert compaction_cfg.compaction_interval == 4

    cache_cfg = build_context_cache_config(cache_intervals=8, ttl_seconds=900, min_tokens=2048)
    assert cache_cfg.cache_intervals == 8
    assert cache_cfg.ttl_seconds == 900
    assert cache_cfg.min_tokens == 2048


def test_sliding_window_and_part_truncation_compaction() -> None:
    """Verify Rubric 2.2: compact_llm_request_history truncates huge parts and summarizes old turns."""
    huge_payload = "ROSTER_DATA_" * 400  # ~4,800 chars
    contents = [
        types.Content(role="user", parts=[types.Part.from_text(text=f"Turn {i} query")])
        if i % 2 == 0
        else types.Content(
            role="model",
            parts=[types.Part.from_text(text=huge_payload if i == 1 else f"Turn {i} reply")],
        )
        for i in range(14)
    ]
    req = LlmRequest(contents=contents)

    stats = compact_llm_request_history(req, max_contents=6, max_chars_per_part=1000)
    assert stats["original_turns"] == 14
    assert stats["final_turns"] == 6
    assert stats["truncated_parts"] >= 1
    assert stats["compacted_turns"] == 9
    assert "[COMPACTED HISTORY SUMMARY" in req.contents[0].parts[0].text
    assert req.contents[-1].parts[0].text == "Turn 13 reply"


@pytest.mark.asyncio
async def test_persistent_sqlite_session_service(tmp_path: Path) -> None:
    """Verify Rubric 2.3: SqliteSessionService persists sessions and state across instances."""
    db_file = tmp_path / "test_sessions.db"

    service_1 = create_persistent_session_service(db_path=db_file)
    created = await service_1.create_session(
        app_name="fantasy_agent",
        user_id="manager_alex",
        state={"active_team_id": "team_alpha", "scoring_format": "Half-PPR"},
        session_id="sess_week8",
    )
    assert created.id == "sess_week8"

    # Re-open a fresh service instance pointing to the same SQLite DB file
    service_2 = create_persistent_session_service(db_path=db_file)
    reloaded = await service_2.get_session(
        app_name="fantasy_agent",
        user_id="manager_alex",
        session_id="sess_week8",
    )
    assert reloaded is not None
    assert reloaded.id == "sess_week8"
    assert reloaded.state["active_team_id"] == "team_alpha"
    assert reloaded.state["scoring_format"] == "Half-PPR"


@pytest.mark.asyncio
async def test_persistent_fantasy_memory_store_and_async_consolidation(tmp_path: Path) -> None:
    """Verify Rubric 2.3 & 2.4: PersistentFantasyMemoryStore persists facts and consolidates async."""
    mem_db = tmp_path / "fantasy_mem.db"
    store = PersistentFantasyMemoryStore(db_path=mem_db)

    await store.upsert_user_fact_async("manager_alex", "default_team", "team_alpha")
    await store.upsert_user_fact_async(
        "manager_alex", "trade_targets", ["Sam LaPorta", "Dallas Goedert"]
    )

    facts = await store.get_user_facts_async("manager_alex")
    assert facts["default_team"] == "team_alpha"
    assert "Sam LaPorta" in facts["trade_targets"]

    # Schedule non-blocking background session consolidation
    task = store.schedule_background_consolidation(
        session_id="sess_week8",
        user_id="manager_alex",
        team_id="team_alpha",
        summary_text="Evaluated bench WR Ladd McConkey and TE trade target Sam LaPorta.",
        turn_count=4,
    )
    assert task is not None
    await task

    summary = await store.get_session_summary_async("sess_week8")
    assert summary is not None
    assert summary["team_id"] == "team_alpha"
    assert summary["turn_count"] == 4
    assert "Sam LaPorta" in summary["summary_text"]
