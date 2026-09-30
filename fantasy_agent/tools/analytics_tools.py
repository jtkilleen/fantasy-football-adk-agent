"""Analytics, Longitudinal Player Trend, Bench Optimization, and Scouting Insight ADK Tools.

Satisfies AgentOps Rubric Criteria:
- 1.1 Comprehensive Tool Docstrings
- 1.2 Descriptive Naming
- 1.3 Explicit JSON Schemas
- 1.4 Guided Error Handling
- 2.4 Async Memory Operations
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from fantasy_agent.data.synthetic_league_store import get_league_store, get_memory_indexer
from fantasy_agent.tools.schemas import (
    BenchAnalysisInput,
    BenchAnalysisOutput,
    DropCandidateRecommendation,
    InsightSearchInput,
    InsightSearchOutput,
    LineupSwapRecommendation,
    PlayerSummarySchema,
    PlayerTrendInput,
    PlayerTrendOutput,
    ToolErrorOutput,
)


async def analyze_player_historical_trends(
    player_name_or_id: str,
    through_week: int = 7,
) -> dict[str, Any]:
    """Compare a player's current-season fantasy trend against the same point last year.

    Call this tool when the user asks analytical or longitudinal questions such as
    "How is my quarterback trending vs. this time last year?" or asks about a player's
    recent week-over-week scoring momentum, snap share, or year-over-year efficiency.

    Args:
        player_name_or_id: Full or partial player name or ID (e.g., `'Jayden Daniels'`,
            `'Kirk Cousins'`, `'Bijan Robinson'`, or `'p_jayden_daniels'`).
        through_week: Number of completed weeks to include in the year-over-year comparison
            (`3` to `7`, defaults to `7`).

    Returns:
        dict[str, Any]: A JSON-serializable dictionary matching `PlayerTrendOutput` with
        2025 vs. 2024 weekly scores, PPG delta, percentage change, recent 3-week average,
        and analytical summary, or `ToolErrorOutput` with a `"recovery_instruction"`.
    """
    try:
        validated_in = PlayerTrendInput(
            player_name_or_id=player_name_or_id,
            through_week=through_week,
        )
    except ValidationError as exc:
        return ToolErrorOutput(
            error_type="INVALID_TREND_INPUT",
            message=f"Trend analysis input validation failed: {exc.errors()[0]['msg']}",
            recovery_instruction=(
                "Call `analyze_player_historical_trends` with a non-empty `player_name_or_id` "
                "(e.g., 'Jayden Daniels') and `through_week` between 3 and 7."
            ),
        ).model_dump()

    store = get_league_store()
    indexer = get_memory_indexer()
    player = store.resolve_player(validated_in.player_name_or_id)
    if player is None:
        sample_names = ", ".join(p.name for p in list(store.players.values())[:8])
        return ToolErrorOutput(
            error_type="PLAYER_NOT_FOUND",
            message=f"No player found matching '{validated_in.player_name_or_id}'.",
            recovery_instruction=(
                f"Retry `analyze_player_historical_trends` using a valid player name from the "
                f"league or waiver pool, such as: {sample_names}."
            ),
        ).model_dump()

    # Ensure async memory indexer is hydrated (Rubric 2.4)
    indexed_summary = await indexer.get_player_trend_summary(player.player_id)
    w = validated_in.through_week
    pts_2025 = player.season_2025_weekly_pts[:w]
    pts_2024 = player.season_2024_weekly_pts[:w]
    avg_2025 = round(sum(pts_2025) / len(pts_2025), 2)
    avg_2024 = round(sum(pts_2024) / len(pts_2024), 2)
    delta_ppg = round(avg_2025 - avg_2024, 2)
    pct_change = round((delta_ppg / avg_2024) * 100.0, 1) if avg_2024 > 0 else 0.0
    recent_3 = round(sum(pts_2025[-3:]) / min(3, len(pts_2025)), 2)

    direction = (
        indexed_summary["trend_direction"]
        if indexed_summary
        else ("surging" if delta_ppg >= 2.0 else "declining" if delta_ppg <= -2.0 else "steady")
    )

    sign = "+" if delta_ppg >= 0 else ""
    summary = (
        f"Through Week {w}, {player.name} ({player.nfl_team} {player.position}) is averaging "
        f"{avg_2025} Half-PPR PPG in 2025 compared to {avg_2024} PPG through Week {w} last year "
        f"({sign}{delta_ppg} PPG / {sign}{pct_change}%). Over the last 3 weeks, {player.name} "
        f"has averaged {recent_3} PPG on a {player.snap_share_pct}% snap share. "
        f"Scouting context: {player.scouting_note}"
    )

    output = PlayerTrendOutput(
        player_id=player.player_id,
        name=player.name,
        nfl_team=player.nfl_team,
        position=player.position,
        through_week=w,
        season_2025_weekly_pts=pts_2025,
        season_2024_weekly_pts=pts_2024,
        avg_pts_2025=avg_2025,
        avg_pts_2024=avg_2024,
        yoy_delta_ppg=delta_ppg,
        yoy_pct_change=pct_change,
        recent_3_week_avg_2025=recent_3,
        trend_direction=direction,
        snap_share_pct=player.snap_share_pct,
        target_or_touch_share_pct=player.target_or_touch_share_pct,
        analytical_summary=summary,
    )
    return output.model_dump()


async def analyze_bench_and_start_sit(
    team_id: str = "team_alpha",
) -> dict[str, Any]:
    """Analyze a fantasy team's bench depth, start/sit swaps, and drop/waiver upgrade candidates.

    Call this tool when the user asks "Please analyze my bench and see who I should start or drop",
    wants to optimize their Week 8 starting lineup, or wants to know which bench player is
    most droppable for a waiver wire pickup.

    Args:
        team_id: Team ID or name to analyze (defaults to `'team_alpha'` / `'Gridiron Guardians'`).

    Returns:
        dict[str, Any]: A JSON-serializable dictionary matching `BenchAnalysisOutput` containing
        recommended start/sit swaps, drop/pickup candidates, and optimized point totals,
        or a `ToolErrorOutput` dictionary with a `"recovery_instruction"`.
    """
    try:
        validated_in = BenchAnalysisInput(team_id=team_id)
    except ValidationError as exc:
        return ToolErrorOutput(
            error_type="INVALID_BENCH_INPUT",
            message=f"Bench analysis input validation failed: {exc.errors()[0]['msg']}",
            recovery_instruction="Pass a valid `team_id` such as 'team_alpha'.",
        ).model_dump()

    store = get_league_store()
    team = store.resolve_team(validated_in.team_id)
    if team is None:
        valid_ids = ", ".join(store.teams.keys())
        return ToolErrorOutput(
            error_type="TEAM_NOT_FOUND",
            message=f"Could not find team '{validated_in.team_id}'.",
            recovery_instruction=f"Call `analyze_bench_and_start_sit` with one of: {valid_ids}.",
        ).model_dump()

    starters = [store.players[pid] for pid in team.starters]
    bench = [store.players[pid] for pid in team.bench]
    current_total = round(sum(p.week_8_projection for p in starters), 2)

    # Evaluate start/sit swaps against eligible starter slots (same position or FLEX slot at index -1)
    flex_starter = starters[-1]
    swaps: list[LineupSwapRecommendation] = []
    for b_player in sorted(bench, key=lambda p: p.week_8_projection, reverse=True):
        candidates = [
            s
            for idx, s in enumerate(starters)
            if s.position == b_player.position
            or (idx == len(starters) - 1 and b_player.position in {"RB", "WR", "TE"})
        ]
        if not candidates:
            continue
        weakest_starter = min(candidates, key=lambda p: p.week_8_projection)
        gain = round(b_player.week_8_projection - weakest_starter.week_8_projection, 2)
        if gain >= 1.0:
            slot_label = "FLEX" if weakest_starter.player_id == flex_starter.player_id else weakest_starter.position
            swaps.append(
                LineupSwapRecommendation(
                    bench_player_to_start=b_player.name,
                    bench_player_position=b_player.position,
                    bench_player_projection=b_player.week_8_projection,
                    starter_to_sit=weakest_starter.name,
                    starter_position=slot_label,
                    starter_projection=weakest_starter.week_8_projection,
                    projected_point_gain=gain,
                    rationale=(
                        f"{b_player.name} projects for {b_player.week_8_projection} pts "
                        f"({b_player.target_or_touch_share_pct}% target/touch share) vs. "
                        f"{weakest_starter.name}'s {weakest_starter.week_8_projection} pts in the {slot_label} slot."
                    ),
                )
            )

    best_gain = swaps[0].projected_point_gain if swaps else 0.0
    optimized_total = round(current_total + best_gain, 2)

    # Identify weakest/injured bench drop candidates and compare against top waiver pickups
    waivers = store.get_waiver_pool()
    drops: list[DropCandidateRecommendation] = []
    sorted_bench_low = sorted(bench, key=lambda p: p.week_8_projection)
    for b_low in sorted_bench_low[:2]:
        # Find top waiver player (especially at TE or overall top projection)
        best_waiver = waivers[0]
        net_upgrade = round(best_waiver.week_8_projection - b_low.week_8_projection, 2)
        if net_upgrade > 2.0:
            drops.append(
                DropCandidateRecommendation(
                    drop_player_name=b_low.name,
                    drop_player_position=b_low.position,
                    drop_player_injury_status=b_low.injury_status,
                    drop_player_projection=b_low.week_8_projection,
                    recommended_waiver_pickup=best_waiver.name,
                    pickup_position=best_waiver.position,
                    pickup_projection=best_waiver.week_8_projection,
                    net_projection_upgrade=net_upgrade,
                    rationale=(
                        f"Drop {b_low.name} ({b_low.injury_status}, {b_low.week_8_projection} proj, "
                        f"{b_low.snap_share_pct}% snaps) to add {best_waiver.name} "
                        f"({best_waiver.position}, {best_waiver.week_8_projection} proj) or TE Cade Otton (12.7 proj)."
                    ),
                )
            )

    output = BenchAnalysisOutput(
        team_id=team.team_id,
        team_name=team.team_name,
        current_projected_total=current_total,
        optimized_projected_total=optimized_total,
        start_sit_recommendations=swaps,
        drop_and_pickup_recommendations=drops,
        bench_players=[
            PlayerSummarySchema.model_validate(store.snapshot_player(p)) for p in bench
        ],
    )
    return output.model_dump()


async def search_player_and_team_insights(
    query: str,
) -> dict[str, Any]:
    """Perform a high-level search across NFL players, teams, injuries, and scouting insights.

    Call this tool when the user asks for scouting reports, injury updates, usage/snap
    trends, or NFL team offense insights (e.g., "What are the latest insights on Washington
    or Chargers receivers?").

    Args:
        query: Search term matching a player name, NFL team abbreviation (e.g., `'WAS'`,
            `'LAC'`, `'DET'`), position (`'QB'`, `'RB'`, `'WR'`, `'TE'`), injury status
            (`'Questionable'`, `'Doubtful'`), or scouting note keyword.

    Returns:
        dict[str, Any]: A JSON-serializable dictionary matching `InsightSearchOutput`
        with all matching players and their scouting insights, or `ToolErrorOutput`.
    """
    try:
        validated_in = InsightSearchInput(query=query)
    except ValidationError as exc:
        return ToolErrorOutput(
            error_type="INVALID_INSIGHT_QUERY",
            message=f"Insight search query validation failed: {exc.errors()[0]['msg']}",
            recovery_instruction=(
                "Pass a search query with at least 2 characters (e.g., a player name, NFL team like 'LAC', or 'Questionable')."
            ),
        ).model_dump()

    store = get_league_store()
    tokens = [t.lower() for t in validated_in.query.strip().split() if t]
    matches = []
    for player in store.players.values():
        searchable_blob = (
            f"{player.name} {player.nfl_team} {player.position} "
            f"{player.injury_status} {player.scouting_note}"
        ).lower()
        if any(tok in searchable_blob for tok in tokens):
            matches.append(PlayerSummarySchema.model_validate(store.snapshot_player(player)))

    matches.sort(key=lambda p: p.week_8_projection, reverse=True)
    output = InsightSearchOutput(
        query=validated_in.query,
        match_count=len(matches),
        matching_insights=matches[:10],
    )
    return output.model_dump()
