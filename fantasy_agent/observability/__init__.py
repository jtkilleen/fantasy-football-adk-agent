"""Observability, Structured JSON Logging, OpenTelemetry Tracing, and PII Redaction package."""

from fantasy_agent.observability.logging import (
    clear_captured_json_logs,
    configure_structured_logging,
    get_captured_json_logs,
    get_structured_logger,
)
from fantasy_agent.observability.pii_redactor import (
    PIIRedactor,
    get_pii_redactor,
    structlog_pii_redaction_processor,
)
from fantasy_agent.observability.tracing import (
    clear_exported_spans,
    configure_tracing,
    get_exported_spans,
    get_tracer,
    trace_and_log_after_model,
    trace_and_log_after_tool,
    trace_and_log_before_model,
    trace_and_log_before_tool,
)

__all__ = [
    "PIIRedactor",
    "clear_captured_json_logs",
    "clear_exported_spans",
    "configure_structured_logging",
    "configure_tracing",
    "get_captured_json_logs",
    "get_exported_spans",
    "get_pii_redactor",
    "get_structured_logger",
    "get_tracer",
    "structlog_pii_redaction_processor",
    "trace_and_log_after_model",
    "trace_and_log_after_tool",
    "trace_and_log_before_model",
    "trace_and_log_before_tool",
]
