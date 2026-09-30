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
