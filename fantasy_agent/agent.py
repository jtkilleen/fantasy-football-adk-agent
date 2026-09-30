"""Root ADK agent entrypoint for the Fantasy Football Personal Agent."""

from __future__ import annotations

from google.adk.agents import LlmAgent

from fantasy_agent.config import get_settings
from fantasy_agent.prompts import COORDINATOR_CONSTITUTION
from fantasy_agent.tools import (
    compare_weekly_matchup,
    fetch_fantasy_league_rosters,
    search_available_waiver_players,
)


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
        tools=[
            fetch_fantasy_league_rosters,
            compare_weekly_matchup,
            search_available_waiver_players,
        ],
    )


root_agent = build_root_agent()
