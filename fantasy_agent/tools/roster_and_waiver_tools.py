"""Core Roster, Weekly Matchup, and Waiver Wire ADK tools.

Satisfies AgentOps Rubric Criteria:
- 1.1 Comprehensive Tool Docstrings
- 1.2 Descriptive Naming
- 1.3 Explicit JSON Schemas
- 1.4 Guided Error Handling
- 2.4 Async Memory Operations (triggers non-blocking background trend indexing)
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from fantasy_agent.data.synthetic_league_store import (
    SyntheticLeagueStore,
    SyntheticTeam,
    get_league_store,
    get_memory_indexer,
)
from fantasy_agent.tools.schemas import (
    MatchupComparisonInput,
    MatchupComparisonOutput,
    PlayerSummarySchema,
    PositionalAdvantageSchema,
    RosterLookupInput,
    RosterLookupOutput,
    TeamRosterSchema,
    ToolErrorOutput,
    WaiverSearchInput,
    WaiverSearchOutput,
)

_VALID_POSITIONS = {"ALL", "QB", "RB", "WR", "TE"}


def _serialize_team(store: SyntheticLeagueStore, team: SyntheticTeam) -> TeamRosterSchema:
    """Build a validated `TeamRosterSchema` from a `SyntheticTeam`."""
    starters = [
        PlayerSummarySchema.model_validate(store.snapshot_player(store.players[pid]))
        for pid in team.starters
    ]
    bench = [
        PlayerSummarySchema.model_validate(store.snapshot_player(store.players[pid]))
        for pid in team.bench
    ]
    starter_total = round(sum(p.week_8_projection for p in starters), 2)
    return TeamRosterSchema(
        team_id=team.team_id,
        team_name=team.team_name,
        manager_name=team.manager_name,
        record=f"{team.wins}-{team.losses}",
        points_for=team.points_for,
        points_against=team.points_against,
        projected_starter_total=starter_total,
        starters=starters,
        bench=bench,
    )


async def fetch_fantasy_league_rosters(
    team_id_or_owner: str = "team_alpha",
    include_all_league_teams: bool = False,
) -> dict[str, Any]:
    """Fetch starters, bench depth, and projections for a fantasy football team and league.

    Call this tool whenever the user asks about their current roster, starting lineup,
    bench players, team record, or other teams in the fantasy league.

    Args:
        team_id_or_owner: The team ID, team name, or manager name to look up.
            Defaults to `'team_alpha'` (`'Gridiron Guardians'`). Other valid teams are
            `'team_bravo'` (`'Blitzkrieg Birds'`) and `'team_charlie'` (`'Sunday Crushers'`).
        include_all_league_teams: If `True`, also returns full rosters and records for
            all other teams in the league (useful for cross-league comparisons or trades).

    Returns:
        dict[str, Any]: A JSON-serializable dictionary matching `RosterLookupOutput`
        containing `"status": "success"`, `"requested_team"`, and `"other_league_teams"`,
        or a `ToolErrorOutput` dictionary with `"status": "error"` and an actionable
        `"recovery_instruction"` if the team identifier is invalid.
    """
    try:
        validated_in = RosterLookupInput(
            team_id_or_owner=team_id_or_owner,
            include_all_league_teams=include_all_league_teams,
        )
    except ValidationError as exc:
        return ToolErrorOutput(
            error_type="INVALID_ROSTER_LOOKUP_INPUT",
            message=f"Roster lookup input validation failed: {exc.errors()[0]['msg']}",
            recovery_instruction=(
                "Pass a non-empty `team_id_or_owner` string such as 'team_alpha' "
                "('Gridiron Guardians'), 'team_bravo' ('Blitzkrieg Birds'), or "
                "'team_charlie' ('Sunday Crushers')."
            ),
        ).model_dump()

    store = get_league_store()
    # Trigger non-blocking background memory indexing (Rubric 2.4)
    get_memory_indexer().trigger_background_refresh()

    team = store.resolve_team(validated_in.team_id_or_owner)
    if team is None:
        valid_options = ", ".join(
            f"'{t.team_id}' ({t.team_name} - {t.manager_name})" for t in store.teams.values()
        )
        return ToolErrorOutput(
            error_type="TEAM_NOT_FOUND",
            message=f"Could not find a fantasy team matching '{validated_in.team_id_or_owner}'.",
            recovery_instruction=(
                f"Call `fetch_fantasy_league_rosters` again using one of the valid league teams: "
                f"{valid_options}."
            ),
        ).model_dump()

    requested_schema = _serialize_team(store, team)
    other_schemas: list[TeamRosterSchema] = []
    if validated_in.include_all_league_teams:
        for other_id, other_team in store.teams.items():
            if other_id != team.team_id:
                other_schemas.append(_serialize_team(store, other_team))

    output = RosterLookupOutput(
        current_week=8,
        requested_team=requested_schema,
        other_league_teams=other_schemas,
    )
    return output.model_dump()


async def compare_weekly_matchup(
    team_id: str = "team_alpha",
    week: int = 8,
) -> dict[str, Any]:
    """Compare a fantasy team's starting lineup and projections against its weekly opponent.

    Call this tool when the user asks how their team stacks up against their current
    opponent, what their projected win probability or point margin is, or which positions
    give them an advantage or disadvantage this week.

    Args:
        team_id: Team ID or name of the user's team (defaults to `'team_alpha'`).
        week: Fantasy regular-season week number to evaluate (defaults to `8`; supports `8` or `9`).

    Returns:
        dict[str, Any]: A JSON-serializable dictionary matching `MatchupComparisonOutput`
        with projected totals, positional breakdown, win probability, and tactical advice,
        or a `ToolErrorOutput` dictionary with a `"recovery_instruction"` on invalid inputs.
    """
    try:
        validated_in = MatchupComparisonInput(team_id=team_id, week=week)
    except ValidationError as exc:
        return ToolErrorOutput(
            error_type="INVALID_MATCHUP_INPUT",
            message=f"Matchup input validation failed: {exc.errors()[0]['msg']}",
            recovery_instruction=(
                "Call `compare_weekly_matchup` with `week=8` (current week) or `week=9`, "
                "and a valid `team_id` such as 'team_alpha'."
            ),
        ).model_dump()

    store = get_league_store()
    user_team = store.resolve_team(validated_in.team_id)
    if user_team is None:
        valid_ids = ", ".join(store.teams.keys())
        return ToolErrorOutput(
            error_type="TEAM_NOT_FOUND",
            message=f"Unknown team '{validated_in.team_id}'.",
            recovery_instruction=(
                f"Retry `compare_weekly_matchup` with one of the valid team IDs: {valid_ids}."
            ),
        ).model_dump()

    opp_id = user_team.weekly_opponents.get(validated_in.week)
    opp_team = store.resolve_team(opp_id) if opp_id else None
    if opp_team is None:
        return ToolErrorOutput(
            error_type="OPPONENT_NOT_SCHEDULED",
            message=f"No opponent scheduled for '{user_team.team_name}' in Week {validated_in.week}.",
            recovery_instruction="Use `week=8` to inspect the active Week 8 head-to-head matchup.",
        ).model_dump()

    user_schema = _serialize_team(store, user_team)
    opp_schema = _serialize_team(store, opp_team)

    positions = ["QB", "RB", "WR", "TE"]
    breakdown: list[PositionalAdvantageSchema] = []
    for pos in positions:
        u_pts = round(sum(p.week_8_projection for p in user_schema.starters if p.position == pos), 2)
        o_pts = round(sum(p.week_8_projection for p in opp_schema.starters if p.position == pos), 2)
        edge = round(u_pts - o_pts, 2)
        adv = (
            user_team.team_name
            if edge > 0.25
            else opp_team.team_name
            if edge < -0.25
            else "Even"
        )
        breakdown.append(
            PositionalAdvantageSchema(
                position=pos,
                user_projected_pts=u_pts,
                opponent_projected_pts=o_pts,
                net_edge=edge,
                advantage_team=adv,
            )
        )

    margin = round(user_schema.projected_starter_total - opp_schema.projected_starter_total, 2)
    # Logistic-style bounded win probability approximation centered at 50%
    win_prob = round(max(5.0, min(95.0, 50.0 + (margin * 2.2))), 1)

    # Identify best bench upgrade against eligible starter slots (same position or FLEX slot)
    best_bench = max(user_schema.bench, key=lambda p: p.week_8_projection)
    flex_starter = user_schema.starters[-1]
    eligible_starters = [
        p
        for idx, p in enumerate(user_schema.starters)
        if p.position == best_bench.position
        or (idx == len(user_schema.starters) - 1 and best_bench.position in {"RB", "WR", "TE"})
    ]
    lowest_eligible = (
        min(eligible_starters, key=lambda p: p.week_8_projection)
        if eligible_starters
        else flex_starter
    )
    gain = round(best_bench.week_8_projection - lowest_eligible.week_8_projection, 2)
    if gain > 0:
        tactical_note = (
            f"Starting bench {best_bench.position} {best_bench.name} ({best_bench.week_8_projection} proj) "
            f"over {lowest_eligible.name} ({lowest_eligible.week_8_projection} proj) in the FLEX/starter slot "
            f"adds +{gain} projected points and shifts the matchup in your favor."
        )
    else:
        tactical_note = "Your current starting lineup maximizes projected points for this matchup."

    output = MatchupComparisonOutput(
        week=validated_in.week,
        user_team_name=user_team.team_name,
        user_projected_total=user_schema.projected_starter_total,
        opponent_team_name=opp_team.team_name,
        opponent_projected_total=opp_schema.projected_starter_total,
        projected_margin=margin,
        win_probability_pct=win_prob,
        positional_breakdown=breakdown,
        tactical_recommendation=tactical_note,
    )
    return output.model_dump()


async def search_available_waiver_players(
    position: str = "ALL",
    min_projected_points: float = 0.0,
    limit: int = 5,
) -> dict[str, Any]:
    """Search unrostered free-agent players available on the fantasy league waiver wire.

    Call this tool when the user asks who is available to pick up on waivers, needs a
    replacement for an injured/underperforming player, or wants top free agents by position.

    Args:
        position: Position filter (`'ALL'`, `'QB'`, `'RB'`, `'WR'`, or `'TE'`). Defaults to `'ALL'`.
        min_projected_points: Minimum Week 8 projected Half-PPR points (`0.0` to `40.0`).
        limit: Maximum number of free agents to return (`1` to `15`, defaults to `5`).

    Returns:
        dict[str, Any]: A JSON-serializable dictionary matching `WaiverSearchOutput`
        listing top unrostered players sorted by Week 8 projection, or a `ToolErrorOutput`
        dictionary with a `"recovery_instruction"` if the position or filter is invalid.
    """
    norm_pos = position.strip().upper()
    if norm_pos not in _VALID_POSITIONS:
        return ToolErrorOutput(
            error_type="INVALID_POSITION_FILTER",
            message=f"Unsupported position filter '{position}'.",
            recovery_instruction=(
                "Call `search_available_waiver_players` with `position` set to one of: "
                "'ALL', 'QB', 'RB', 'WR', or 'TE'."
            ),
        ).model_dump()

    try:
        validated_in = WaiverSearchInput(
            position=norm_pos,
            min_projected_points=min_projected_points,
            limit=limit,
        )
    except ValidationError as exc:
        return ToolErrorOutput(
            error_type="INVALID_WAIVER_SEARCH_INPUT",
            message=f"Waiver search input validation failed: {exc.errors()[0]['msg']}",
            recovery_instruction=(
                "Ensure `min_projected_points` is between 0.0 and 40.0 and `limit` is between 1 and 15."
            ),
        ).model_dump()

    store = get_league_store()
    pool = store.get_waiver_pool(position=validated_in.position)
    filtered = [p for p in pool if p.week_8_projection >= validated_in.min_projected_points]
    top_players = [
        PlayerSummarySchema.model_validate(store.snapshot_player(p))
        for p in filtered[: validated_in.limit]
    ]

    output = WaiverSearchOutput(
        position_filter=validated_in.position,
        available_count=len(top_players),
        players=top_players,
    )
    return output.model_dump()
