"""Unit tests for Milestone 5: Structured JSON Logging, Intent/Outcome Capture, OpenTelemetry, and PII Redaction."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from fantasy_agent.callbacks import (
    enforce_hitl_before_tool_callback,
    enforce_input_and_domain_guardrails,
    enforce_output_self_eval_guardrail,
    trace_and_log_after_tool,
)
from fantasy_agent.memory import PersistentFantasyMemoryStore
from fantasy_agent.observability import (
    PIIRedactor,
    clear_captured_json_logs,
    clear_exported_spans,
    configure_structured_logging,
    get_captured_json_logs,
    get_exported_spans,
    get_structured_logger,
)


def test_structured_json_logging_and_pii_redaction() -> None:
    """Verify Rubric 4.1 & 4.4: Structured JSON logs capture rich metadata and scrub PII."""
    configure_structured_logging(force=True)
    clear_captured_json_logs()

    logger = get_structured_logger("test_logger")
    logger.info(
        "user_profile_loaded",
        session_id="sess_101",
        agent_name="fantasy_football_coordinator",
        user_email="alex.rivera@example.com",
        user_phone="415-555-0199",
        api_key="AIzaSySecretKeyValue1234567890",
        nested_contact={"ssn": "123-45-6789", "note": "Call 800-555-1234"},
    )

    logs = get_captured_json_logs()
    assert len(logs) >= 1
    entry = logs[-1]
    assert entry["event"] == "user_profile_loaded"
    assert entry["session_id"] == "sess_101"
    assert entry["level"] == "info"
    assert "timestamp" in entry
    assert entry["user_email"] == "[REDACTED_EMAIL]"
    assert entry["user_phone"] == "[REDACTED_PHONE]"
    assert entry["api_key"] == "[REDACTED_SECRET]"
    assert entry["nested_contact"]["ssn"] == "[REDACTED_SECRET]"
    assert entry["nested_contact"]["note"] == "Call [REDACTED_PHONE]"


def test_intent_vs_outcome_capture_and_opentelemetry_spans() -> None:
    """Verify Rubric 4.2 & 4.3: Explicit intent/outcome capture and linked OpenTelemetry spans."""
    configure_structured_logging(force=True)
    clear_captured_json_logs()
    clear_exported_spans()

    # 1. Model Intent -> Model Outcome
    cb_ctx = MagicMock()
    cb_ctx.agent_name = "analytics_trend_agent"
    cb_ctx.invocation_id = "inv_777"
    cb_ctx.state = {}

    req = LlmRequest(
        contents=[
            types.Content(
                role="user",
                parts=[types.Part.from_text(text="How is Jayden Daniels trending?")],
            )
        ]
    )
    enforce_input_and_domain_guardrails(cb_ctx, req)

    resp = LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text="Jayden Daniels is averaging 23.4 PPG (+24.5%).")],
        )
    )
    enforce_output_self_eval_guardrail(cb_ctx, resp)

    # 2. Tool Intent -> Tool Outcome
    mock_tool = MagicMock()
    mock_tool.name = "analyze_player_historical_trends"
    tool_ctx = MagicMock()
    tool_ctx.agent_name = "analytics_trend_agent"
    tool_ctx.function_call_id = "fc_888"
    tool_ctx.state = {}
    tool_args = {"player_name_or_id": "Jayden Daniels", "through_week": 7}

    enforce_hitl_before_tool_callback(mock_tool, tool_args, tool_ctx)
    trace_and_log_after_tool(
        mock_tool,
        tool_args,
        tool_ctx,
        {"status": "success", "avg_pts_2025": 23.4},
    )

    logs = get_captured_json_logs()
    events = [entry["event"] for entry in logs]
    assert "model_intent" in events
    assert "model_outcome" in events
    assert "tool_intent" in events
    assert "tool_outcome" in events

    tool_intent_log = next(e for e in logs if e["event"] == "tool_intent")
    tool_outcome_log = next(e for e in logs if e["event"] == "tool_outcome")
    assert tool_intent_log["lifecycle_phase"] == "intent"
    assert tool_intent_log["intended_args"]["player_name_or_id"] == "Jayden Daniels"
    assert tool_outcome_log["lifecycle_phase"] == "outcome"
    assert tool_outcome_log["outcome_status"] == "success"
    assert "latency_ms" in tool_outcome_log
    assert "trace_id" in tool_outcome_log

    # Verify OpenTelemetry spans were created and finished
    spans = get_exported_spans()
    span_names = {s.name for s in spans}
    assert "agent.model.analytics_trend_agent" in span_names
    assert "agent.tool.analyze_player_historical_trends" in span_names


@pytest.mark.asyncio
async def test_memory_pipeline_pii_redaction(tmp_path: Path) -> None:
    """Verify Rubric 4.4: Memory pipeline scrubs PII before writing to persistent SQLite store."""
    mem_db = tmp_path / "pii_mem.db"
    store = PersistentFantasyMemoryStore(db_path=mem_db)

    await store.upsert_user_fact_async(
        "manager_alex",
        "contact_info",
        {"email": "alex@secretdomain.com", "phone": "555-867-5309"},
    )
    await store.consolidate_session_summary_async(
        session_id="sess_pii",
        user_id="manager_alex",
        team_id="team_alpha",
        summary_text="User email alex@secretdomain.com asked about trade with SSN 123-45-6789.",
        turn_count=2,
    )

    facts = await store.get_user_facts_async("manager_alex")
    assert facts["contact_info"]["email"] == "[REDACTED_EMAIL]"
    assert facts["contact_info"]["phone"] == "[REDACTED_PHONE]"

    summary = await store.get_session_summary_async("sess_pii")
    assert summary is not None
    assert "[REDACTED_EMAIL]" in summary["summary_text"]
    assert "[REDACTED_SSN]" in summary["summary_text"]
    assert "alex@secretdomain.com" not in summary["summary_text"]


def test_pii_redactor_bearer_and_card() -> None:
    """Verify PIIRedactor scrubs bearer tokens and credit card numbers."""
    redactor = PIIRedactor(use_cloud_dlp=False)
    sample = "Token: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 and card 4111-2222-3333-4444"
    clean = redactor.redact_string(sample)
    assert "[REDACTED_SECRET_TOKEN]" in clean
    assert "[REDACTED_CARD]" in clean
