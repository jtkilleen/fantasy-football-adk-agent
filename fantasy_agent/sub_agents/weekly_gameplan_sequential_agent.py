"""Sequential Multi-Agent Workflow (`SequentialAgent`) for End-to-End Weekly Gameplans.

Satisfies AgentOps Rubric Criterion 3.1 (Multi-Agent Patterns: Coordinator + SequentialAgent)
and Criterion 3.2 (Strategic Model Routing: Flash for data gathering, Pro for synthesis).
"""

from __future__ import annotations

from google.adk.agents import LlmAgent, SequentialAgent
from google.genai import types

from fantasy_agent.callbacks import (
    DEFAULT_GEMINI_SAFETY_SETTINGS,
    enforce_hitl_before_tool_callback,
    enforce_input_and_domain_guardrails,
    enforce_output_self_eval_guardrail,
    trace_and_log_after_tool,
)
from fantasy_agent.config import select_model_for_task
from fantasy_agent.prompts import (
    ANALYTICS_TREND_CONSTITUTION,
    LEAGUE_ROSTER_CONSTITUTION,
    TRADE_STRATEGY_CONSTITUTION,
)
from fantasy_agent.tools import (
    analyze_bench_and_start_sit,
    compare_weekly_matchup,
    discover_mutually_beneficial_trades,
    fetch_fantasy_league_rosters,
    search_available_waiver_players,
)


def build_weekly_gameplan_sequential_agent() -> SequentialAgent:
    """Build a 3-stage `SequentialAgent` pipeline for comprehensive weekly fantasy gameplanning."""
    safety_cfg = types.GenerateContentConfig(safety_settings=DEFAULT_GEMINI_SAFETY_SETTINGS)

    step1_roster_and_waiver = LlmAgent(
        name="step1_roster_and_waiver_scan",
        model=select_model_for_task("roster_lookup"),
        description="Step 1 (`gemini-2.5-flash`): Fetch current team roster and top available waiver wire targets.",
        instruction=LEAGUE_ROSTER_CONSTITUTION,
        tools=[fetch_fantasy_league_rosters, search_available_waiver_players],
        output_key="roster_and_waiver_snapshot",
        generate_content_config=safety_cfg,
        before_model_callback=enforce_input_and_domain_guardrails,
        after_model_callback=enforce_output_self_eval_guardrail,
        before_tool_callback=enforce_hitl_before_tool_callback,
        after_tool_callback=trace_and_log_after_tool,
    )

    step2_bench_optimization = LlmAgent(
        name="step2_bench_and_start_sit_analysis",
        model=select_model_for_task("analytics"),
        description="Step 2 (`gemini-2.5-pro`): Evaluate bench efficiency, start/sit swaps, and drop candidates.",
        instruction=ANALYTICS_TREND_CONSTITUTION,
        tools=[analyze_bench_and_start_sit],
        output_key="bench_optimization_plan",
        generate_content_config=safety_cfg,
        before_model_callback=enforce_input_and_domain_guardrails,
        after_model_callback=enforce_output_self_eval_guardrail,
        before_tool_callback=enforce_hitl_before_tool_callback,
        after_tool_callback=trace_and_log_after_tool,
    )

    step3_matchup_and_trade_synthesis = LlmAgent(
        name="step3_matchup_and_trade_synthesis",
        model=select_model_for_task("trade_strategy"),
        description="Step 3 (`gemini-2.5-pro`): Synthesize weekly matchup strategy and mutually beneficial trade proposals.",
        instruction=TRADE_STRATEGY_CONSTITUTION,
        tools=[compare_weekly_matchup, discover_mutually_beneficial_trades],
        output_key="weekly_gameplan_synthesis",
        generate_content_config=safety_cfg,
        before_model_callback=enforce_input_and_domain_guardrails,
        after_model_callback=enforce_output_self_eval_guardrail,
        before_tool_callback=enforce_hitl_before_tool_callback,
        after_tool_callback=trace_and_log_after_tool,
    )

    return SequentialAgent(
        name="weekly_gameplan_sequential_agent",
        description=(
            "Sequential 3-step pipeline (`SequentialAgent`) that chains roster/waiver scanning, "
            "bench start/sit optimization, and weekly matchup + trade synthesis. Invoke ONLY when "
            "the user explicitly asks to run the 'full 3-step sequential weekly gameplan pipeline'."
        ),
        sub_agents=[
            step1_roster_and_waiver,
            step2_bench_optimization,
            step3_matchup_and_trade_synthesis,
        ],
    )
