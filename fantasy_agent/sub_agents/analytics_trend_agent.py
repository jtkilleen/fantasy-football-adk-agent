"""Analytics, Longitudinal Player Trend & Bench Optimization Sub-Agent (`gemini-2.5-pro`).

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
from fantasy_agent.prompts import ANALYTICS_TREND_CONSTITUTION
from fantasy_agent.tools import (
    analyze_bench_and_start_sit,
    analyze_player_historical_trends,
    commit_lineup_waiver_or_trade_action,
    fetch_fantasy_league_rosters,
    search_player_and_team_insights,
)


def build_analytics_trend_agent() -> LlmAgent:
    """Build the deep-reasoning Analytics & Trend sub-agent (`gemini-2.5-pro`)."""
    return LlmAgent(
        name="analytics_trend_agent",
        model=select_model_for_task("analytics"),
        description=(
            "Specialist analytical agent for year-over-year player trend comparisons "
            "(e.g., how a quarterback is trending vs. last year), bench start/sit and "
            "drop analysis, and NFL player/team scouting insights."
        ),
        instruction=ANALYTICS_TREND_CONSTITUTION,
        tools=[
            fetch_fantasy_league_rosters,
            analyze_player_historical_trends,
            analyze_bench_and_start_sit,
            search_player_and_team_insights,
            commit_lineup_waiver_or_trade_action,
        ],
        before_model_callback=enforce_input_and_domain_guardrails,
        after_model_callback=enforce_output_self_eval_guardrail,
        before_tool_callback=enforce_hitl_before_tool_callback,
    )
