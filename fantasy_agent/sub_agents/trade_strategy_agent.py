"""Trade Discovery, Matchup Comparison & Strategy Sub-Agent (`gemini-2.5-pro`).

Satisfies AgentOps Rubric Criteria 3.1 (Multi-Agent Patterns), 3.2 (Strategic Model Routing),
and 3.4 (Human-in-the-Loop Hooks).
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from fantasy_agent.callbacks import (
    enforce_hitl_before_tool_callback,
    enforce_input_and_domain_guardrails,
    enforce_output_self_eval_guardrail,
    trace_and_log_after_tool,
)
from fantasy_agent.config import select_model_for_task
from fantasy_agent.prompts import TRADE_STRATEGY_CONSTITUTION
from fantasy_agent.tools import (
    commit_lineup_waiver_or_trade_action,
    compare_weekly_matchup,
    discover_mutually_beneficial_trades,
    evaluate_league_trade_proposal,
    fetch_fantasy_league_rosters,
)


def build_trade_strategy_agent() -> LlmAgent:
    """Build the deep-reasoning Trade & Matchup Strategy sub-agent (`gemini-2.5-pro`)."""
    return LlmAgent(
        name="trade_strategy_agent",
        model=select_model_for_task("trade_strategy"),
        description=(
            "Specialist strategy agent for weekly head-to-head opponent matchup comparisons, "
            "discovering mutually beneficial league trades, evaluating trade proposals, and "
            "submitting human-confirmed trade offers."
        ),
        instruction=TRADE_STRATEGY_CONSTITUTION,
        tools=[
            compare_weekly_matchup,
            discover_mutually_beneficial_trades,
            evaluate_league_trade_proposal,
            fetch_fantasy_league_rosters,
            commit_lineup_waiver_or_trade_action,
        ],
        before_model_callback=enforce_input_and_domain_guardrails,
        after_model_callback=enforce_output_self_eval_guardrail,
        before_tool_callback=enforce_hitl_before_tool_callback,
        after_tool_callback=trace_and_log_after_tool,
    )
