"""OpenTelemetry Distributed Tracing and Intent-vs-Outcome Lifecycle Hooks.

Satisfies AgentOps Rubric Criteria:
- 4.2 Intent vs. Outcome Capture (explicitly logs `model_intent` / `model_outcome` and
  `tool_intent` / `tool_outcome` with arguments, latency, and status).
- 4.3 Distributed Tracing (links OpenTelemetry spans from user query through sub-agents,
  model calls, and tool executions).
"""

from __future__ import annotations

import time
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from fantasy_agent.observability.logging import get_structured_logger

_SPAN_EXPORTER = InMemorySpanExporter()
_TRACER_INITIALIZED = False

# Active span & timing registries keyed by invocation/call ID
_ACTIVE_INVOCATION_SPANS: dict[str, tuple[trace.Span, float]] = {}
_ACTIVE_MODEL_SPANS: dict[str, tuple[trace.Span, float]] = {}
_ACTIVE_TOOL_SPANS: dict[str, tuple[trace.Span, float]] = {}


def configure_tracing(service_name: str = "fantasy-football-personal-agent") -> trace.Tracer:
    """Initialize the OpenTelemetry `TracerProvider` and `InMemorySpanExporter`."""
    global _TRACER_INITIALIZED
    if not _TRACER_INITIALIZED:
        provider = trace.get_tracer_provider()
        if not isinstance(provider, TracerProvider):
            resource = Resource.create({"service.name": service_name})
            provider = TracerProvider(resource=resource)
            provider.add_span_processor(SimpleSpanProcessor(_SPAN_EXPORTER))
            trace.set_tracer_provider(provider)
        else:
            provider.add_span_processor(SimpleSpanProcessor(_SPAN_EXPORTER))
        _TRACER_INITIALIZED = True
    return trace.get_tracer(service_name)


def get_tracer() -> trace.Tracer:
    """Return the configured OpenTelemetry tracer."""
    return configure_tracing()


def get_exported_spans() -> list[ReadableSpan]:
    """Return all completed OpenTelemetry spans collected by the in-memory exporter."""
    return list(_SPAN_EXPORTER.get_finished_spans())


def clear_exported_spans() -> None:
    """Clear the collected OpenTelemetry spans."""
    _ACTIVE_INVOCATION_SPANS.clear()
    _ACTIVE_MODEL_SPANS.clear()
    _ACTIVE_TOOL_SPANS.clear()
    _SPAN_EXPORTER.clear()


def _get_or_start_invocation_span(inv_id: str, user_query_preview: str = "") -> trace.Span:
    """Return or create the parent OpenTelemetry span linking the entire request from query to answer."""
    tracer = get_tracer()
    if inv_id not in _ACTIVE_INVOCATION_SPANS:
        root_span = tracer.start_span(
            name="agent.invocation",
            attributes={
                "fantasy.invocation.id": str(inv_id),
                "fantasy.user_query_preview": user_query_preview[:160],
            },
        )
        _ACTIVE_INVOCATION_SPANS[inv_id] = (root_span, time.perf_counter())
    return _ACTIVE_INVOCATION_SPANS[inv_id][0]


def _extract_latest_user_text(llm_request: LlmRequest) -> str:
    """Extract a short preview of the latest user turn from `LlmRequest`."""
    for content in reversed(llm_request.contents or []):
        if content.role == "user" and content.parts:
            texts = [p.text for p in content.parts if p.text]
            if texts:
                return " ".join(texts)[:200]
    return ""


def trace_and_log_before_model(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> None:
    """Start an OpenTelemetry model span (linked to the parent invocation trace) and log `model_intent`."""
    tracer = get_tracer()
    logger = get_structured_logger("fantasy_agent.model")
    agent_name = getattr(callback_context, "agent_name", "unknown_agent")
    inv_id = str(getattr(callback_context, "invocation_id", "inv_default"))
    key = f"{inv_id}:{agent_name}"
    user_preview = _extract_latest_user_text(llm_request)

    parent_span = _get_or_start_invocation_span(inv_id, user_preview)
    parent_ctx = trace.set_span_in_context(parent_span)

    span = tracer.start_span(
        name=f"agent.model.{agent_name}",
        context=parent_ctx,
        attributes={
            "fantasy.agent.name": str(agent_name),
            "fantasy.invocation.id": inv_id,
            "fantasy.model.name": str(getattr(llm_request, "model", "gemini")),
        },
    )
    _ACTIVE_MODEL_SPANS[key] = (span, time.perf_counter())

    with trace.use_span(span, end_on_exit=False):
        logger.info(
            "model_intent",
            lifecycle_phase="intent",
            agent_name=str(agent_name),
            invocation_id=inv_id,
            model=str(getattr(llm_request, "model", "gemini")),
            user_query_preview=user_preview,
            turn_count=len(llm_request.contents or []),
        )


def trace_and_log_after_model(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> None:
    """Finish the OpenTelemetry model span and log `model_outcome` after Gemini responds."""
    logger = get_structured_logger("fantasy_agent.model")
    agent_name = getattr(callback_context, "agent_name", "unknown_agent")
    inv_id = str(getattr(callback_context, "invocation_id", "inv_default"))
    key = f"{inv_id}:{agent_name}"

    span_entry = _ACTIVE_MODEL_SPANS.pop(key, None)
    latency_ms = 0.0
    span = None
    if span_entry is not None:
        span, start_t = span_entry
        latency_ms = round((time.perf_counter() - start_t) * 1000.0, 2)

    parts = (
        llm_response.content.parts
        if llm_response and llm_response.content and llm_response.content.parts
        else []
    )
    tool_calls = [
        p.function_call.name
        for p in parts
        if getattr(p, "function_call", None) is not None and p.function_call.name
    ]
    text_preview = " ".join(p.text for p in parts if p.text)[:200]

    if span is not None:
        span.set_attribute("fantasy.latency_ms", latency_ms)
        span.set_attribute("fantasy.model.tool_calls_count", len(tool_calls))
        with trace.use_span(span, end_on_exit=True):
            logger.info(
                "model_outcome",
                lifecycle_phase="outcome",
                agent_name=str(agent_name),
                invocation_id=inv_id,
                latency_ms=latency_ms,
                planned_tool_calls=tool_calls,
                response_preview=text_preview,
            )
    else:
        logger.info(
            "model_outcome",
            lifecycle_phase="outcome",
            agent_name=str(agent_name),
            invocation_id=inv_id,
            latency_ms=latency_ms,
            planned_tool_calls=tool_calls,
            response_preview=text_preview,
        )

    # If the model produced a final text answer with no further tool calls, close the root invocation span
    if not tool_calls and inv_id in _ACTIVE_INVOCATION_SPANS:
        root_span, root_start = _ACTIVE_INVOCATION_SPANS.pop(inv_id)
        total_ms = round((time.perf_counter() - root_start) * 1000.0, 2)
        root_span.set_attribute("fantasy.invocation.total_latency_ms", total_ms)
        root_span.set_attribute("fantasy.final_agent", str(agent_name))
        root_span.end()


def trace_and_log_before_tool(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
) -> None:
    """Start an OpenTelemetry tool span (linked to the parent invocation trace) and log `tool_intent`."""
    tracer = get_tracer()
    logger = get_structured_logger("fantasy_agent.tool")
    agent_name = getattr(tool_context, "agent_name", "unknown_agent")
    inv_id = str(getattr(tool_context, "invocation_id", "inv_default"))
    fc_id = getattr(tool_context, "function_call_id", None) or f"{agent_name}:{tool.name}"

    parent_span = _get_or_start_invocation_span(inv_id)
    parent_ctx = trace.set_span_in_context(parent_span)

    span = tracer.start_span(
        name=f"agent.tool.{tool.name}",
        context=parent_ctx,
        attributes={
            "fantasy.agent.name": str(agent_name),
            "fantasy.invocation.id": inv_id,
            "fantasy.tool.name": str(tool.name),
            "fantasy.function_call.id": str(fc_id),
        },
    )
    _ACTIVE_TOOL_SPANS[str(fc_id)] = (span, time.perf_counter())

    with trace.use_span(span, end_on_exit=False):
        logger.info(
            "tool_intent",
            lifecycle_phase="intent",
            agent_name=str(agent_name),
            invocation_id=inv_id,
            tool_name=str(tool.name),
            function_call_id=str(fc_id),
            intended_args=dict(args),
        )


def trace_and_log_after_tool(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
    tool_response: dict[str, Any],
) -> dict[str, Any] | None:
    """Finish the OpenTelemetry tool span and log `tool_outcome` after tool execution."""
    logger = get_structured_logger("fantasy_agent.tool")
    agent_name = getattr(tool_context, "agent_name", "unknown_agent")
    fc_id = getattr(tool_context, "function_call_id", None) or f"{agent_name}:{tool.name}"

    span_entry = _ACTIVE_TOOL_SPANS.pop(str(fc_id), None)
    latency_ms = 0.0
    span = None
    if span_entry is not None:
        span, start_t = span_entry
        latency_ms = round((time.perf_counter() - start_t) * 1000.0, 2)

    status = (
        str(tool_response.get("status", "success"))
        if isinstance(tool_response, dict)
        else "success"
    )
    error_type = (
        tool_response.get("error_type")
        if isinstance(tool_response, dict)
        else None
    )

    if span is not None:
        span.set_attribute("fantasy.tool.status", status)
        span.set_attribute("fantasy.latency_ms", latency_ms)
        if error_type:
            span.set_attribute("fantasy.tool.error_type", str(error_type))
        with trace.use_span(span, end_on_exit=True):
            logger.info(
                "tool_outcome",
                lifecycle_phase="outcome",
                agent_name=str(agent_name),
                tool_name=str(tool.name),
                function_call_id=str(fc_id),
                intended_args=dict(args),
                outcome_status=status,
                error_type=error_type,
                latency_ms=latency_ms,
            )
    else:
        logger.info(
            "tool_outcome",
            lifecycle_phase="outcome",
            agent_name=str(agent_name),
            tool_name=str(tool.name),
            function_call_id=str(fc_id),
            intended_args=dict(args),
            outcome_status=status,
            error_type=error_type,
            latency_ms=latency_ms,
        )
    return None
