"""Root ADK Coordinator Agent and Application entrypoint for the Fantasy Football Agent.

Implements:
- History Compaction & Resumability via ADK `App` (`EventsCompactionConfig`, Rubric 2.2)
- Multi-Agent Orchestration (Rubric 3.1)
- Strategic Model Routing (Rubric 3.2)
- Guardrails & Self-Evaluation Callbacks (Rubric 3.3)
- Human-in-the-Loop Hooks (Rubric 3.4)
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.apps.app import App
from google.genai import types

from fantasy_agent.callbacks import (
    DEFAULT_GEMINI_SAFETY_SETTINGS,
    FantasyGuardrailAndPolicyPlugin,
    enforce_hitl_before_tool_callback,
    enforce_input_and_domain_guardrails,
    enforce_output_self_eval_guardrail,
    trace_and_log_after_tool,
)
from fantasy_agent.config import get_settings, select_model_for_task
from fantasy_agent.memory import build_events_compaction_config, build_resumability_config
from fantasy_agent.prompts import COORDINATOR_CONSTITUTION
from fantasy_agent.sub_agents import (
    build_analytics_trend_agent,
    build_league_roster_agent,
    build_trade_strategy_agent,
    build_weekly_gameplan_sequential_agent,
)
from fantasy_agent.tools import (
    analyze_bench_and_start_sit,
    analyze_player_historical_trends,
    commit_lineup_waiver_or_trade_action,
    compare_weekly_matchup,
    discover_mutually_beneficial_trades,
    evaluate_league_trade_proposal,
    fetch_fantasy_league_rosters,
    search_available_waiver_players,
    search_player_and_team_insights,
)


def build_root_agent() -> LlmAgent:
    """Construct the multi-agent Fantasy Football Coordinator (`root_agent`)."""
    get_settings()
    league_roster_agent = build_league_roster_agent()
    analytics_trend_agent = build_analytics_trend_agent()
    trade_strategy_agent = build_trade_strategy_agent()

    return LlmAgent(
        name="fantasy_football_coordinator",
        model=select_model_for_task("routing"),
        description=(
            "Coordinator agent for the Fantasy Football Personal Agent system, orchestrating "
            "specialized sub-agents for roster/waiver management, historical trend & bench "
            "analytics, and weekly matchup & trade strategy."
        ),
        instruction=COORDINATOR_CONSTITUTION,
        sub_agents=[
            league_roster_agent,
            analytics_trend_agent,
            trade_strategy_agent,
        ],
        tools=[
            fetch_fantasy_league_rosters,
            search_available_waiver_players,
            compare_weekly_matchup,
            analyze_player_historical_trends,
            analyze_bench_and_start_sit,
            search_player_and_team_insights,
            discover_mutually_beneficial_trades,
            evaluate_league_trade_proposal,
            commit_lineup_waiver_or_trade_action,
        ],
        generate_content_config=types.GenerateContentConfig(
            safety_settings=DEFAULT_GEMINI_SAFETY_SETTINGS
        ),
        before_model_callback=enforce_input_and_domain_guardrails,
        after_model_callback=enforce_output_self_eval_guardrail,
        before_tool_callback=enforce_hitl_before_tool_callback,
        after_tool_callback=trace_and_log_after_tool,
    )


root_agent = build_root_agent()
weekly_gameplan_sequential_agent = build_weekly_gameplan_sequential_agent()


def build_fantasy_app() -> App:
    """Construct the top-level ADK `App` with `FantasyGuardrailAndPolicyPlugin`, `EventsCompactionConfig`, and `ResumabilityConfig`."""
    return App(
        name="fantasy_agent",
        root_agent=root_agent,
        plugins=[FantasyGuardrailAndPolicyPlugin()],
        events_compaction_config=build_events_compaction_config(),
        resumability_config=build_resumability_config(),
    )


app = build_fantasy_app()
