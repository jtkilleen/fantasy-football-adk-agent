"""Strict Pydantic JSON schemas for Fantasy Football Agent tools.

Satisfies AgentOps Rubric Criterion 1.3 (Explicit JSON Schemas) and Criterion 1.4
(Guided Error Handling via structured recovery instructions).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolErrorOutput(BaseModel):
    """Structured error response with guided recovery instructions for the LLM."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["error"] = "error"
    error_type: str = Field(description="Category of error (e.g., TEAM_NOT_FOUND, INVALID_WEEK).")
    message: str = Field(description="Human-readable explanation of what went wrong.")
    recovery_instruction: str = Field(
        description="Actionable step-by-step instruction telling the LLM how to recover."
    )


class PlayerSummarySchema(BaseModel):
    """Validated player summary schema returned by roster, matchup, and waiver tools."""

    model_config = ConfigDict(extra="forbid")

    player_id: str
    name: str
    nfl_team: str
    position: Literal["QB", "RB", "WR", "TE"]
    injury_status: str
    bye_week: int
    week_8_projection: float
    avg_pts_2025: float
    avg_pts_2024: float
    yoy_delta_ppg: float
    snap_share_pct: float
    target_or_touch_share_pct: float
    strength_of_schedule_rank: int
    scouting_note: str


class RosterLookupInput(BaseModel):
    """Input schema for `fetch_fantasy_league_rosters`."""

    model_config = ConfigDict(extra="forbid")

    team_id_or_owner: str = Field(
        default="team_alpha",
        min_length=2,
        description="Team identifier, team name, or manager name (e.g., 'team_alpha' or 'Gridiron Guardians').",
    )
    include_all_league_teams: bool = Field(
        default=False,
        description="When True, also returns summary standings and rosters for all other teams in the league.",
    )


class TeamRosterSchema(BaseModel):
    """Structured representation of a fantasy team's roster and projections."""

    model_config = ConfigDict(extra="forbid")

    team_id: str
    team_name: str
    manager_name: str
    record: str
    points_for: float
    points_against: float
    projected_starter_total: float
    starters: list[PlayerSummarySchema]
    bench: list[PlayerSummarySchema]


class RosterLookupOutput(BaseModel):
    """Output schema for `fetch_fantasy_league_rosters`."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["success"] = "success"
    current_week: int
    scoring_format: str = "Half-PPR"
    requested_team: TeamRosterSchema
    other_league_teams: list[TeamRosterSchema] = Field(default_factory=list)


class MatchupComparisonInput(BaseModel):
    """Input schema for `compare_weekly_matchup`."""

    model_config = ConfigDict(extra="forbid")

    team_id: str = Field(
        default="team_alpha",
        min_length=2,
        description="Team ID or name of the user's fantasy team (defaults to 'team_alpha').",
    )
    week: int = Field(
        default=8,
        ge=8,
        le=9,
        description="Fantasy week number to compare (supported synthetic schedule weeks: 8 or 9).",
    )


class PositionalAdvantageSchema(BaseModel):
    """Positional comparison between user's team and their opponent."""

    model_config = ConfigDict(extra="forbid")

    position: str
    user_projected_pts: float
    opponent_projected_pts: float
    net_edge: float
    advantage_team: str


class MatchupComparisonOutput(BaseModel):
    """Output schema for `compare_weekly_matchup`."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["success"] = "success"
    week: int
    user_team_name: str
    user_projected_total: float
    opponent_team_name: str
    opponent_projected_total: float
    projected_margin: float
    win_probability_pct: float
    positional_breakdown: list[PositionalAdvantageSchema]
    tactical_recommendation: str


class WaiverSearchInput(BaseModel):
    """Input schema for `search_available_waiver_players`."""

    model_config = ConfigDict(extra="forbid")

    position: str = Field(
        default="ALL",
        description="Position filter: 'ALL', 'QB', 'RB', 'WR', or 'TE'.",
    )
    min_projected_points: float = Field(
        default=0.0,
        ge=0.0,
        le=40.0,
        description="Minimum Week 8 projected points threshold.",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=15,
        description="Maximum number of available free-agent players to return.",
    )


class WaiverSearchOutput(BaseModel):
    """Output schema for `search_available_waiver_players`."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["success"] = "success"
    position_filter: str
    available_count: int
    players: list[PlayerSummarySchema]


# --- Milestone 3: Analytics, Bench, Insights, Trade & HITL Schemas ---


class PlayerTrendInput(BaseModel):
    """Input schema for `analyze_player_historical_trends`."""

    model_config = ConfigDict(extra="forbid")

    player_name_or_id: str = Field(
        min_length=2,
        description="Player name or ID to analyze (e.g., 'Jayden Daniels' or 'p_jayden_daniels').",
    )
    through_week: int = Field(
        default=7,
        ge=3,
        le=7,
        description="Number of completed weeks to compare between 2025 and 2024 (3 to 7).",
    )


class PlayerTrendOutput(BaseModel):
    """Output schema for `analyze_player_historical_trends`."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["success"] = "success"
    player_id: str
    name: str
    nfl_team: str
    position: str
    through_week: int
    season_2025_weekly_pts: list[float]
    season_2024_weekly_pts: list[float]
    avg_pts_2025: float
    avg_pts_2024: float
    yoy_delta_ppg: float
    yoy_pct_change: float
    recent_3_week_avg_2025: float
    trend_direction: Literal["surging", "steady", "declining"]
    snap_share_pct: float
    target_or_touch_share_pct: float
    analytical_summary: str


class BenchAnalysisInput(BaseModel):
    """Input schema for `analyze_bench_and_start_sit`."""

    model_config = ConfigDict(extra="forbid")

    team_id: str = Field(
        default="team_alpha",
        min_length=2,
        description="Team ID or name whose bench and starting lineup should be analyzed.",
    )


class LineupSwapRecommendation(BaseModel):
    """Recommended start/sit swap between a bench player and a current starter."""

    model_config = ConfigDict(extra="forbid")

    bench_player_to_start: str
    bench_player_position: str
    bench_player_projection: float
    starter_to_sit: str
    starter_position: str
    starter_projection: float
    projected_point_gain: float
    rationale: str


class DropCandidateRecommendation(BaseModel):
    """Recommended bench player to drop and top waiver wire replacement."""

    model_config = ConfigDict(extra="forbid")

    drop_player_name: str
    drop_player_position: str
    drop_player_injury_status: str
    drop_player_projection: float
    recommended_waiver_pickup: str
    pickup_position: str
    pickup_projection: float
    net_projection_upgrade: float
    rationale: str


class BenchAnalysisOutput(BaseModel):
    """Output schema for `analyze_bench_and_start_sit`."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["success"] = "success"
    team_id: str
    team_name: str
    current_projected_total: float
    optimized_projected_total: float
    start_sit_recommendations: list[LineupSwapRecommendation]
    drop_and_pickup_recommendations: list[DropCandidateRecommendation]
    bench_players: list[PlayerSummarySchema]


class InsightSearchInput(BaseModel):
    """Input schema for `search_player_and_team_insights`."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        min_length=2,
        description="Search query for player name, NFL team code (e.g., 'WAS', 'LAC'), position, or injury/usage keyword.",
    )


class InsightSearchOutput(BaseModel):
    """Output schema for `search_player_and_team_insights`."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["success"] = "success"
    query: str
    match_count: int
    matching_insights: list[PlayerSummarySchema]


class TradeEvaluationInput(BaseModel):
    """Input schema for `evaluate_league_trade_proposal`."""

    model_config = ConfigDict(extra="forbid")

    proposer_team_id: str = Field(
        default="team_alpha",
        min_length=2,
        description="Team ID or name proposing the trade (defaults to 'team_alpha').",
    )
    partner_team_id: str = Field(
        min_length=2,
        description="Partner team ID or name (e.g., 'team_bravo' or 'team_charlie').",
    )
    send_player_names: list[str] = Field(
        min_length=1,
        description="List of player names or IDs that `proposer_team_id` would send.",
    )
    receive_player_names: list[str] = Field(
        min_length=1,
        description="List of player names or IDs that `proposer_team_id` would receive.",
    )


class TradeEvaluationOutput(BaseModel):
    """Output schema for `evaluate_league_trade_proposal`."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["success"] = "success"
    proposer_team_name: str
    partner_team_name: str
    sent_players: list[PlayerSummarySchema]
    received_players: list[PlayerSummarySchema]
    proposer_weekly_projection_delta: float
    partner_weekly_projection_delta: float
    fairness_verdict: Literal["FAIR_MUTUALLY_BENEFICIAL", "SLIGHTLY_UNBALANCED", "LOPSIDED"]
    positional_fit_analysis: str
    recommendation: str


class TradeSuggestionSchema(BaseModel):
    """A mutually beneficial trade suggestion discovered across the league."""

    model_config = ConfigDict(extra="forbid")

    partner_team_id: str
    partner_team_name: str
    partner_manager: str
    send_player: str
    send_player_position: str
    send_player_projection: float
    receive_player: str
    receive_player_position: str
    receive_player_projection: float
    user_starter_upgrade_pts: float
    why_it_works_for_both_teams: str


class TradeDiscoveryOutput(BaseModel):
    """Output schema for `discover_mutually_beneficial_trades`."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["success"] = "success"
    user_team_name: str
    identified_team_weakness: str
    identified_team_surplus: str
    suggested_trades: list[TradeSuggestionSchema]


class CommitActionInput(BaseModel):
    """Input schema for `commit_lineup_waiver_or_trade_action`."""

    model_config = ConfigDict(extra="forbid")

    action_type: Literal["WAIVER_ADD_DROP", "SET_STARTER_LINEUP", "SUBMIT_TRADE_PROPOSAL"] = Field(
        description="Type of high-stakes roster or trade action to execute."
    )
    team_id: str = Field(
        default="team_alpha",
        min_length=2,
        description="Team ID performing the action.",
    )
    primary_player_name: str = Field(
        min_length=2,
        description="Player being added, moved into starting lineup, or acquired in trade.",
    )
    secondary_player_name: str = Field(
        min_length=2,
        description="Player being dropped, moved to bench, or traded away.",
    )
    partner_team_id: str | None = Field(
        default=None,
        description="Required when `action_type` is 'SUBMIT_TRADE_PROPOSAL'.",
    )
    human_confirmed: bool = Field(
        default=False,
        description=(
            "MUST be False until the user has explicitly confirmed the exact transaction "
            "in conversation. Only set to True after explicit user approval."
        ),
    )


class CommitActionOutput(BaseModel):
    """Output schema for `commit_lineup_waiver_or_trade_action`."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["executed", "pending_human_confirmation"]
    action_type: str
    team_id: str
    summary: str
    requires_confirmation_prompt: str | None = None
