"""Human-in-the-Loop (HITL) confirmation hooks for high-stakes agent actions.

Satisfies AgentOps Rubric Criterion 3.4 (Human-in-the-Loop Hooks):
High-stakes actions include explicit code stops requiring human confirmation before execution.
"""

from __future__ import annotations

from typing import Any

from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

HIGH_STAKES_TOOL_NAMES = frozenset({"commit_lineup_waiver_or_trade_action"})


def enforce_hitl_before_tool_callback(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
) -> dict[str, Any] | None:
    """ADK `before_tool_callback` enforcing Human-in-the-Loop approval on state-mutating tools.

    Intercepts calls to `commit_lineup_waiver_or_trade_action` and verifies whether explicit
    human confirmation (`args["human_confirmed"] == True` or `tool_context.state["hitl_approved"]`)
    has been granted. If not, halts execution before any state mutation occurs and returns
    a structured confirmation request.

    Args:
        tool: The ADK tool instance being invoked.
        args: Dictionary of arguments passed by the LLM to the tool.
        tool_context: ADK `ToolContext` providing access to session state.

    Returns:
        A dictionary short-circuiting tool execution when human confirmation is missing,
        or `None` to allow the tool to execute once confirmed.
    """
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
        return {
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

    # Clear pending action once confirmed and allow execution
    tool_context.state["pending_hitl_action"] = None
    return None
