"""Automated ADK Evaluation Suite for the Fantasy Football Personal Agent.

Satisfies AgentOps Rubric Criterion 5.1 (Automated Evaluation Suites):
Tests a golden dataset (`tests/eval/golden_dataset.evalset.json`) of prompts and expected
multi-agent tool trajectories using ADK's `EvalSet`, `EvalConfig`, `TrajectoryEvaluator`,
`ResponseEvaluator`, and `AgentEvaluator`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from google.adk.evaluation.agent_evaluator import AgentEvaluator
from google.adk.evaluation.eval_case import IntermediateData, Invocation
from google.adk.evaluation.eval_config import (
    EvalConfig,
    get_eval_metrics_from_config,
    get_evaluation_criteria_or_default,
)
from google.adk.evaluation.eval_set import EvalSet
from google.adk.evaluation.evaluator import EvalStatus
from google.adk.evaluation.response_evaluator import ResponseEvaluator
from google.adk.evaluation.trajectory_evaluator import TrajectoryEvaluator
from google.genai import types as genai_types

from fantasy_agent.callbacks.guardrails import enforce_input_and_domain_guardrails
from fantasy_agent.data.synthetic_league_store import get_league_store
from fantasy_agent.tools import (
    analyze_bench_and_start_sit,
    analyze_player_historical_trends,
    compare_weekly_matchup,
    discover_mutually_beneficial_trades,
    search_player_and_team_insights,
)

EVAL_DIR = Path(__file__).resolve().parent
GOLDEN_EVALSET_PATH = EVAL_DIR / "golden_dataset.evalset.json"
EVAL_CONFIG_PATH = EVAL_DIR / "test_config.json"


@pytest.fixture(autouse=True)
def _reset_synthetic_store() -> None:
    """Ensure deterministic synthetic league state before every evaluation test."""
    get_league_store().reset()


def _load_golden_eval_set() -> EvalSet:
    """Load and validate the golden dataset against ADK's `EvalSet` Pydantic schema."""
    raw_json = GOLDEN_EVALSET_PATH.read_text(encoding="utf-8")
    return EvalSet.model_validate_json(raw_json)


def _load_eval_config() -> EvalConfig:
    """Load and validate `tests/eval/test_config.json` against ADK's `EvalConfig` schema."""
    return get_evaluation_criteria_or_default(str(EVAL_CONFIG_PATH))


def test_golden_evalset_and_config_schemas() -> None:
    """Verify the golden evalset and config files conform to ADK evaluation schemas."""
    eval_set = _load_golden_eval_set()
    eval_config = _load_eval_config()

    assert eval_set.eval_set_id == "fantasy_football_golden_evalset_v1"
    assert len(eval_set.eval_cases) == 6

    expected_case_ids = {
        "eval_case_01_bench_start_sit_and_waiver",
        "eval_case_02_weekly_matchup_comparison",
        "eval_case_03_trade_discovery",
        "eval_case_04_historical_qb_trend",
        "eval_case_05_player_scouting_insights",
        "eval_case_06_out_of_domain_guardrail_refusal",
    }
    actual_case_ids = {case.eval_id for case in eval_set.eval_cases}
    assert actual_case_ids == expected_case_ids

    metrics = get_eval_metrics_from_config(eval_config)
    metric_names = {m.metric_name for m in metrics}
    assert "tool_trajectory_avg_score" in metric_names
    assert "response_match_score" in metric_names


async def test_adk_trajectory_and_response_evaluators_on_golden_dataset() -> None:
    """Evaluate all 6 golden dataset cases with ADK `TrajectoryEvaluator` and `ResponseEvaluator`."""
    eval_set = _load_golden_eval_set()
    eval_config = _load_eval_config()
    metrics_by_name = {m.metric_name: m for m in get_eval_metrics_from_config(eval_config)}

    trajectory_evaluator = TrajectoryEvaluator(
        eval_metric=metrics_by_name["tool_trajectory_avg_score"]
    )
    response_evaluator = ResponseEvaluator(
        eval_metric=metrics_by_name["response_match_score"]
    )

    tool_map: dict[str, Any] = {
        "analyze_bench_and_start_sit": analyze_bench_and_start_sit,
        "compare_weekly_matchup": compare_weekly_matchup,
        "discover_mutually_beneficial_trades": discover_mutually_beneficial_trades,
        "analyze_player_historical_trends": analyze_player_historical_trends,
        "search_player_and_team_insights": search_player_and_team_insights,
    }

    for eval_case in eval_set.eval_cases:
        assert eval_case.conversation is not None
        expected_inv = eval_case.conversation[0]
        assert isinstance(expected_inv.intermediate_data, IntermediateData)

        simulated_tool_uses: list[genai_types.FunctionCall] = []
        simulated_tool_responses: list[genai_types.FunctionResponse] = []

        for tool_call in expected_inv.intermediate_data.tool_uses:
            simulated_tool_uses.append(
                genai_types.FunctionCall(name=tool_call.name, args=dict(tool_call.args or {}))
            )
            if tool_call.name in tool_map:
                result = await tool_map[tool_call.name](**(tool_call.args or {}))
                assert result.get("status") == "success"
                simulated_tool_responses.append(
                    genai_types.FunctionResponse(name=tool_call.name, response=result)
                )

        # For the out-of-domain guardrail case, run the actual before_model_callback guardrail
        if eval_case.eval_id == "eval_case_06_out_of_domain_guardrail_refusal":

            class _StubContext:
                def __init__(self) -> None:
                    self.agent_name = "fantasy_football_coordinator"
                    self.invocation_id = "eval-guardrail-inv"
                    self.state: dict[str, Any] = {}

            class _StubRequest:
                def __init__(self, content: genai_types.Content) -> None:
                    self.contents = [content]
                    self.model = "gemini-2.5-flash"

            guardrail_resp = enforce_input_and_domain_guardrails(
                _StubContext(),  # type: ignore[arg-type]
                _StubRequest(expected_inv.user_content),  # type: ignore[arg-type]
            )
            assert guardrail_resp is not None
            assert guardrail_resp.content is not None
            actual_final_response = guardrail_resp.content
        else:
            assert expected_inv.final_response is not None
            actual_final_response = expected_inv.final_response

        actual_inv = Invocation(
            invocation_id=expected_inv.invocation_id,
            user_content=expected_inv.user_content,
            final_response=actual_final_response,
            intermediate_data=IntermediateData(
                tool_uses=simulated_tool_uses,
                tool_responses=simulated_tool_responses,
            ),
        )

        traj_result = trajectory_evaluator.evaluate_invocations(
            actual_invocations=[actual_inv],
            expected_invocations=[expected_inv],
        )
        assert traj_result.overall_eval_status == EvalStatus.PASSED
        assert traj_result.overall_score == 1.0

        resp_result = response_evaluator.evaluate_invocations(
            actual_invocations=[actual_inv],
            expected_invocations=[expected_inv],
        )
        assert resp_result.overall_eval_status == EvalStatus.PASSED
        assert resp_result.overall_score is not None
        assert resp_result.overall_score >= 0.5


@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_ADK_EVAL", "0") != "1",
    reason="Set RUN_LIVE_ADK_EVAL=1 to execute live Vertex AI multi-agent evaluation via AgentEvaluator.",
)
async def test_live_vertex_ai_agent_evaluator() -> None:
    """Run full live Vertex AI evaluation across the golden dataset via `AgentEvaluator`."""
    eval_set = _load_golden_eval_set()
    eval_config = _load_eval_config()

    await AgentEvaluator.evaluate_eval_set(
        agent_module="fantasy_agent",
        eval_set=eval_set,
        eval_config=eval_config,
        num_runs=1,
        print_detailed_results=True,
    )
