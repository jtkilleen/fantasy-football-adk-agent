"""Root ADK agent entrypoint for the Fantasy Football Personal Agent."""

from __future__ import annotations

from google.adk.agents import LlmAgent

from fantasy_agent.config import get_settings
from fantasy_agent.prompts import COORDINATOR_CONSTITUTION


def build_root_agent() -> LlmAgent:
    """Construct and configure the root Fantasy Football Personal Agent."""
    settings = get_settings()
    return LlmAgent(
        name="fantasy_football_coordinator",
        model=settings.fast_model,
        description=(
            "Personal fantasy football assistant that manages rosters, waiver pickups, "
            "weekly opponent matchup comparisons, player trend analytics, and trade proposals."
        ),
        instruction=COORDINATOR_CONSTITUTION,
    )


root_agent = build_root_agent()
