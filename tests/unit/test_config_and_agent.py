"""Unit tests for Milestone 1: Config, Secret Manager loader, Constitution, and Root Agent."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fantasy_agent.agent import build_root_agent, root_agent
from fantasy_agent.config import (
    FAST_MODEL,
    REASONING_MODEL,
    fetch_secret_from_secret_manager,
    get_settings,
    resolve_gcp_project_id,
)
from fantasy_agent.prompts import COORDINATOR_CONSTITUTION


def test_constitution_includes_core_sections() -> None:
    """Verify Rubric 2.1: Robust system instructions define persona, domain, and boundaries."""
    assert "Persona & Role" in COORDINATOR_CONSTITUTION
    assert "Half-PPR" in COORDINATOR_CONSTITUTION
    assert "Strict Tool Grounding" in COORDINATOR_CONSTITUTION
    assert "Human-in-the-Loop Confirmation" in COORDINATOR_CONSTITUTION


def test_secret_manager_env_override(monkeypatch) -> None:
    """Verify Rubric 5.3: Environment variable override works cleanly for offline testing."""
    monkeypatch.setenv("TEST_SECRET_KEY", "env-secret-value")
    val = fetch_secret_from_secret_manager("TEST_SECRET_KEY", project_id="test-proj")
    assert val == "env-secret-value"


def test_secret_manager_gcp_client_call(monkeypatch) -> None:
    """Verify Rubric 5.3: Secret Manager client retrieves payload when env var is absent."""
    monkeypatch.delenv("CLOUD_SECRET_KEY", raising=False)
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.payload.data = b"secret-from-gcp\n"
    mock_client.access_secret_version.return_value = mock_response

    with patch(
        "fantasy_agent.config.secretmanager.SecretManagerServiceClient",
        return_value=mock_client,
    ):
        val = fetch_secret_from_secret_manager(
            "CLOUD_SECRET_KEY",
            project_id="my-gcp-project",
            version_id="2",
        )

    assert val == "secret-from-gcp"
    mock_client.access_secret_version.assert_called_once_with(
        request={"name": "projects/my-gcp-project/secrets/CLOUD_SECRET_KEY/versions/2"}
    )


def test_resolve_gcp_project_id_from_env(monkeypatch) -> None:
    """Verify project ID resolves from GOOGLE_CLOUD_PROJECT environment variable."""
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "unit-test-project")
    assert resolve_gcp_project_id() == "unit-test-project"


def test_root_agent_initialization() -> None:
    """Verify root_agent initializes as an ADK LlmAgent with expected model and instructions."""
    settings = get_settings()
    assert settings.fast_model == FAST_MODEL
    assert settings.reasoning_model == REASONING_MODEL

    agent = build_root_agent()
    assert agent.name == "fantasy_football_coordinator"
    assert agent.model == FAST_MODEL
    assert "Half-PPR" in agent.instruction
    assert root_agent.name == "fantasy_football_coordinator"
