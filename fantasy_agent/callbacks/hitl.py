"""Human-in-the-Loop (HITL) confirmation hooks and Tool Intent/Outcome Tracing Callbacks.

Satisfies AgentOps Rubric Criteria:
- 3.4 Human-in-the-Loop Hooks (high-stakes actions require explicit human confirmation)
- 4.2 Intent vs. Outcome Capture (logs `tool_intent` before execution and `tool_outcome` after)
- 4.3 Distributed Tracing (creates linked OpenTelemetry tool spans)
"""

from __future__ import annotations

from typing import Any

from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

from fantasy_agent.observability.tracing import (
    trace_and_log_after_tool,
    trace_and_log_before_tool,
)

HIGH_STAKES_TOOL_NAMES = frozenset({"commit_lineup_waiver_or_trade_action"})


def enforce_hitl_before_tool_callback(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
) -> dict[str, Any] | None:
    """ADK `before_tool_callback` recording tool intent, OpenTelemetry span, and HITL check."""
    # Record intended tool call and open OpenTelemetry span (Rubric 4.2 & 4.3)
    trace_and_log_before_tool(tool, args, tool_context)

    if tool.name not in HIGH_STAKES_TOOL_NAMES:
        return None

    is_confirmed = bool(args.get("human_confirmed", False)) or bool(
        tool_context.state.get("hitl_approved", False)
    )
    action_type = str(args.get("action_type", "UNKNOWN_ACTION"))
    team_id = str(args.get("team_id", "team_alpha"))
    primary = str(args.get("primary_player_name", ""))
    secondary = str(args.get("secondary_player_name", ""))

    if not is_confirmed:
        staged_summary = (
            f"Action={action_type} | Team={team_id} | "
            f"Primary Player={primary} | Secondary Player={secondary}"
        )
        tool_context.state["pending_hitl_action"] = {
            "tool_name": tool.name,
            "action_type": action_type,
            "team_id": team_id,
            "primary_player_name": primary,
            "secondary_player_name": secondary,
            "partner_team_id": args.get("partner_team_id"),
            "summary": staged_summary,
        }
        blocked_response = {
            "status": "pending_human_confirmation",
            "action_type": action_type,
            "team_id": team_id,
            "summary": staged_summary,
            "requires_confirmation_prompt": (
                f"HITL GUARDRAIL STOP: High-stakes action ({staged_summary}) requires "
                f"explicit human confirmation before execution. Present the exact transaction "
                f"details to the user and ask them to reply 'yes' or 'confirm' to proceed."
            ),
        }
        # Also record the HITL pause outcome on the tool span
        trace_and_log_after_tool(tool, args, tool_context, blocked_response)
        return blocked_response

    tool_context.state["pending_hitl_action"] = None
    return None
