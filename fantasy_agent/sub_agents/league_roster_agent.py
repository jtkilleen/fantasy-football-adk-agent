"""League & Waiver Wire Specialist Sub-Agent (`gemini-2.5-flash`).

Satisfies AgentOps Rubric Criteria 3.1 (Multi-Agent Patterns) and 3.2 (Strategic Model Routing).
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from fantasy_agent.callbacks import (
    enforce_hitl_before_tool_callback,
    enforce_input_and_domain_guardrails,
    enforce_output_self_eval_guardrail,
)
from fantasy_agent.config import select_model_for_task
from fantasy_agent.prompts import LEAGUE_ROSTER_CONSTITUTION
from fantasy_agent.tools import (
    commit_lineup_waiver_or_trade_action,
    fetch_fantasy_league_rosters,
    search_available_waiver_players,
)


def build_league_roster_agent() -> LlmAgent:
    """Build the fast League & Waiver Wire sub-agent (`gemini-2.5-flash`)."""
    return LlmAgent(
        name="league_roster_agent",
        model=select_model_for_task("fast"),
        description=(
            "Specialist agent for looking up fantasy league rosters, searching available "
            "waiver wire free agents, and executing confirmed lineup or waiver transactions."
        ),
        instruction=LEAGUE_ROSTER_CONSTITUTION,
        tools=[
            fetch_fantasy_league_rosters,
            search_available_waiver_players,
            commit_lineup_waiver_or_trade_action,
        ],
        before_model_callback=enforce_input_and_domain_guardrails,
        after_model_callback=enforce_output_self_eval_guardrail,
        before_tool_callback=enforce_hitl_before_tool_callback,
    )
