"""Unit tests for Milestone 2: Synthetic League Store, Schemas, Async Indexer, and Tools."""

from __future__ import annotations

import pytest

from fantasy_agent.data.synthetic_league_store import (
    AsyncFantasyMemoryIndexer,
    SyntheticLeagueStore,
)
from fantasy_agent.tools.roster_and_waiver_tools import (
    compare_weekly_matchup,
    fetch_fantasy_league_rosters,
    search_available_waiver_players,
)
from fantasy_agent.tools.schemas import (
    MatchupComparisonOutput,
    RosterLookupOutput,
    ToolErrorOutput,
    WaiverSearchOutput,
)


def test_tool_docstrings_and_descriptive_names() -> None:
    """Verify Rubric 1.1 & 1.2: Comprehensive docstrings and descriptive action names."""
    tools = [
        fetch_fantasy_league_rosters,
        compare_weekly_matchup,
        search_available_waiver_players,
    ]
    for fn in tools:
        assert fn.__doc__ is not None
        assert "Args:" in fn.__doc__
        assert "Returns:" in fn.__doc__
        assert len(fn.__name__) >= 18


@pytest.mark.asyncio
async def test_fetch_fantasy_league_rosters_valid_schema() -> None:
    """Verify Rubric 1.3: Roster tool returns data conforming to RosterLookupOutput schema."""
    res = await fetch_fantasy_league_rosters("team_alpha", include_all_league_teams=True)
    validated = RosterLookupOutput.model_validate(res)
    assert validated.status == "success"
    assert validated.requested_team.team_name == "Gridiron Guardians"
    assert len(validated.requested_team.starters) == 7
    assert len(validated.requested_team.bench) == 4
    assert len(validated.other_league_teams) == 2


@pytest.mark.asyncio
async def test_fetch_fantasy_league_rosters_guided_error() -> None:
    """Verify Rubric 1.4: Unknown team returns structured error + actionable recovery_instruction."""
    res = await fetch_fantasy_league_rosters("nonexistent_team_xyz")
    err = ToolErrorOutput.model_validate(res)
    assert err.status == "error"
    assert err.error_type == "TEAM_NOT_FOUND"
    assert "team_alpha" in err.recovery_instruction
    assert "Gridiron Guardians" in err.recovery_instruction


@pytest.mark.asyncio
async def test_compare_weekly_matchup_valid_and_error() -> None:
    """Verify weekly matchup comparison schema and guided error handling for invalid weeks."""
    res = await compare_weekly_matchup(team_id="team_alpha", week=8)
    validated = MatchupComparisonOutput.model_validate(res)
    assert validated.user_team_name == "Gridiron Guardians"
    assert validated.opponent_team_name == "Blitzkrieg Birds"
    assert len(validated.positional_breakdown) == 4
    assert "Ladd McConkey" in validated.tactical_recommendation

    # Invalid week triggers guided error recovery
    bad_week = await compare_weekly_matchup(team_id="team_alpha", week=99)
    err = ToolErrorOutput.model_validate(bad_week)
    assert err.error_type == "INVALID_MATCHUP_INPUT"
    assert "week=8" in err.recovery_instruction


@pytest.mark.asyncio
async def test_search_available_waiver_players_valid_and_error() -> None:
    """Verify waiver search filters by position and returns guided error on invalid position."""
    res = await search_available_waiver_players(position="RB", min_projected_points=10.0, limit=3)
    validated = WaiverSearchOutput.model_validate(res)
    assert validated.status == "success"
    assert validated.available_count >= 1
    assert validated.players[0].name == "Tyrone Tracy Jr."
    assert all(p.position == "RB" for p in validated.players)

    bad_pos = await search_available_waiver_players(position="KICKER")
    err = ToolErrorOutput.model_validate(bad_pos)
    assert err.error_type == "INVALID_POSITION_FILTER"
    assert "'QB', 'RB', 'WR', or 'TE'" in err.recovery_instruction


@pytest.mark.asyncio
async def test_async_memory_indexer_background_operation() -> None:
    """Verify Rubric 2.4: AsyncFantasyMemoryIndexer runs asynchronously in the background."""
    store = SyntheticLeagueStore()
    indexer = AsyncFantasyMemoryIndexer(store)
    assert not indexer.is_indexed

    task = indexer.trigger_background_refresh()
    assert task is not None
    await task
    assert indexer.is_indexed

    daniels_trend = await indexer.get_player_trend_summary("p_jayden_daniels")
    assert daniels_trend is not None
    assert daniels_trend["trend_direction"] == "surging"
    assert daniels_trend["yoy_delta_ppg"] > 4.0
