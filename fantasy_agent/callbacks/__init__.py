"""ADK lifecycle callbacks for guardrails, HITL enforcement, and OpenTelemetry tracing."""

from fantasy_agent.callbacks.guardrails import (
    DEFAULT_GEMINI_SAFETY_SETTINGS,
    FantasyGuardrailAndPolicyPlugin,
    enforce_input_and_domain_guardrails,
    enforce_output_self_eval_guardrail,
    scrub_text_pii,
)
from fantasy_agent.callbacks.hitl import (
    HIGH_STAKES_TOOL_NAMES,
    enforce_hitl_before_tool_callback,
    trace_and_log_after_tool,
)

__all__ = [
    "DEFAULT_GEMINI_SAFETY_SETTINGS",
    "HIGH_STAKES_TOOL_NAMES",
    "FantasyGuardrailAndPolicyPlugin",
    "enforce_hitl_before_tool_callback",
    "enforce_input_and_domain_guardrails",
    "enforce_output_self_eval_guardrail",
    "scrub_text_pii",
    "trace_and_log_after_tool",
]
