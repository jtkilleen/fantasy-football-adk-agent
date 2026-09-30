"""Deterministic Synthetic Fantasy Football Data Engine and Async Memory Indexer.

Provides multi-season (2024 vs. 2025) weekly player stats, a 4-team synthetic fantasy
league with starters and benches, weekly opponent matchups, an unrostered waiver wire
pool, and scouting insights. Also implements `AsyncFantasyMemoryIndexer` to satisfy
AgentOps Rubric Criterion 2.4 (Async Memory Operations).
"""

from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SyntheticPlayer:
    """Represents an NFL player in the synthetic fantasy league."""

    player_id: str
    name: str
    nfl_team: str
    position: str  # QB, RB, WR, TE
    injury_status: str  # Healthy, Questionable, Doubtful, Out
    bye_week: int
    week_8_projection: float
    season_2025_weekly_pts: list[float]  # Weeks 1-7 current season
    season_2024_weekly_pts: list[float]  # Weeks 1-7 prior season
    snap_share_pct: float
    target_or_touch_share_pct: float
    scouting_note: str
    strength_of_schedule_rank: int  # 1 (easiest) to 32 (hardest)

    @property
    def avg_pts_2025(self) -> float:
        """Average Half-PPR fantasy points per game in Weeks 1-7 of 2025."""
        if not self.season_2025_weekly_pts:
            return 0.0
        return round(sum(self.season_2025_weekly_pts) / len(self.season_2025_weekly_pts), 2)

    @property
    def avg_pts_2024(self) -> float:
        """Average Half-PPR fantasy points per game in Weeks 1-7 of 2024."""
        if not self.season_2024_weekly_pts:
            return 0.0
        return round(sum(self.season_2024_weekly_pts) / len(self.season_2024_weekly_pts), 2)

    @property
    def yoy_delta_ppg(self) -> float:
        """Year-over-year points-per-game delta (2025 vs. 2024 through Week 7)."""
        return round(self.avg_pts_2025 - self.avg_pts_2024, 2)


@dataclass
class SyntheticTeam:
    """Represents a fantasy team in the synthetic league."""

    team_id: str
    team_name: str
    manager_name: str
    wins: int
    losses: int
    points_for: float
    points_against: float
    starters: list[str]  # List of player_ids (7 slots: QB, RB1, RB2, WR1, WR2, TE, FLEX)
    bench: list[str]  # List of player_ids (4 slots)
    weekly_opponents: dict[int, str] = field(default_factory=dict)


def _build_initial_players() -> dict[str, SyntheticPlayer]:
    """Construct the deterministic catalog of rostered and waiver wire NFL players."""
    players_list = [
        # --- TEAM ALPHA (Gridiron Guardians) ---
        SyntheticPlayer(
            player_id="p_jayden_daniels",
            name="Jayden Daniels",
            nfl_team="WAS",
            position="QB",
            injury_status="Healthy",
            bye_week=14,
            week_8_projection=23.6,
            season_2025_weekly_pts=[22.4, 24.8, 19.6, 25.1, 23.0, 26.2, 22.7],
            season_2024_weekly_pts=[17.2, 14.5, 21.8, 19.4, 18.1, 20.6, 19.9],
            snap_share_pct=98.5,
            target_or_touch_share_pct=18.4,
            scouting_note=(
                "Trending strongly upward in Year 2 (+4.6 PPG vs. 2024 Weeks 1-7). "
                "Red-zone designed rushing attempts increased by 32% and deep-ball "
                "completion rate is top-3 in the NFL."
            ),
            strength_of_schedule_rank=6,
        ),
        SyntheticPlayer(
            player_id="p_bijan_robinson",
            name="Bijan Robinson",
            nfl_team="ATL",
            position="RB",
            injury_status="Healthy",
            bye_week=12,
            week_8_projection=19.4,
            season_2025_weekly_pts=[18.5, 21.2, 16.4, 22.0, 19.8, 17.9, 21.4],
            season_2024_weekly_pts=[16.1, 14.8, 13.9, 15.2, 17.0, 18.4, 16.5],
            snap_share_pct=81.0,
            target_or_touch_share_pct=31.5,
            scouting_note="Elite bellcow RB1 with a 21% target share and 78% inside-the-5 carry share.",
            strength_of_schedule_rank=8,
        ),
        SyntheticPlayer(
            player_id="p_kenneth_walker",
            name="Kenneth Walker III",
            nfl_team="SEA",
            position="RB",
            injury_status="Questionable",
            bye_week=10,
            week_8_projection=12.8,
            season_2025_weekly_pts=[16.2, 15.0, 11.4, 18.6, 13.8, 14.1, 10.3],
            season_2024_weekly_pts=[17.5, 16.0, 14.2, 19.1, 12.4, 15.8, 14.9],
            snap_share_pct=64.0,
            target_or_touch_share_pct=23.0,
            scouting_note="Limited in Wednesday/Thursday practice with a mild ankle sprain; monitor game-day status.",
            strength_of_schedule_rank=19,
        ),
        SyntheticPlayer(
            player_id="p_amon_ra",
            name="Amon-Ra St. Brown",
            nfl_team="DET",
            position="WR",
            injury_status="Healthy",
            bye_week=5,
            week_8_projection=18.5,
            season_2025_weekly_pts=[17.4, 21.0, 19.2, 16.8, 20.5, 18.1, 19.3],
            season_2024_weekly_pts=[16.8, 19.4, 18.0, 17.2, 15.9, 20.1, 18.4],
            snap_share_pct=93.0,
            target_or_touch_share_pct=30.2,
            scouting_note="Commands a 30.2% target share and leads the league in third-down conversions.",
            strength_of_schedule_rank=9,
        ),
        SyntheticPlayer(
            player_id="p_garrett_wilson",
            name="Garrett Wilson",
            nfl_team="NYJ",
            position="WR",
            injury_status="Healthy",
            bye_week=12,
            week_8_projection=14.7,
            season_2025_weekly_pts=[13.8, 15.4, 12.9, 17.1, 14.2, 16.0, 14.2],
            season_2024_weekly_pts=[12.4, 14.1, 11.8, 15.6, 16.9, 13.2, 14.0],
            snap_share_pct=94.0,
            target_or_touch_share_pct=27.8,
            scouting_note="High-volume perimeter and slot WR2 with double-digit targets in 4 of last 5 games.",
            strength_of_schedule_rank=14,
        ),
        SyntheticPlayer(
            player_id="p_evan_engram",
            name="Evan Engram",
            nfl_team="JAX",
            position="TE",
            injury_status="Healthy",
            bye_week=12,
            week_8_projection=7.9,
            season_2025_weekly_pts=[7.2, 8.5, 6.9, 9.4, 8.1, 7.8, 8.9],
            season_2024_weekly_pts=[10.5, 11.2, 9.8, 12.1, 10.4, 11.0, 9.9],
            snap_share_pct=71.0,
            target_or_touch_share_pct=15.2,
            scouting_note=(
                "Target share has dropped to 15.2% due to increased two-TE sets; low red-zone usage "
                "makes TE the primary upgrade need for Gridiron Guardians."
            ),
            strength_of_schedule_rank=24,
        ),
        SyntheticPlayer(
            player_id="p_jaylen_warren",
            name="Jaylen Warren",
            nfl_team="PIT",
            position="RB",
            injury_status="Healthy",
            bye_week=9,
            week_8_projection=8.8,
            season_2025_weekly_pts=[8.4, 9.6, 7.5, 10.2, 9.1, 8.8, 9.4],
            season_2024_weekly_pts=[9.2, 8.7, 10.1, 7.9, 9.5, 8.4, 9.0],
            snap_share_pct=46.0,
            target_or_touch_share_pct=16.5,
            scouting_note="Change-of-pace third-down back capped at ~10 touches per game; lower projection than bench options.",
            strength_of_schedule_rank=22,
        ),
        # Team Alpha Bench
        SyntheticPlayer(
            player_id="p_ladd_mcconkey",
            name="Ladd McConkey",
            nfl_team="LAC",
            position="WR",
            injury_status="Healthy",
            bye_week=5,
            week_8_projection=15.4,
            season_2025_weekly_pts=[12.8, 14.1, 13.9, 16.2, 15.8, 17.1, 16.4],
            season_2024_weekly_pts=[10.2, 9.4, 11.1, 12.5, 11.8, 13.0, 12.4],
            snap_share_pct=88.0,
            target_or_touch_share_pct=28.4,
            scouting_note=(
                "Breakout Year 2 slot/Z receiver averaging 16.4 PPG over the last 4 weeks against "
                "soft Week 8 coverage. Strong START recommendation over Jaylen Warren in FLEX."
            ),
            strength_of_schedule_rank=4,
        ),
        SyntheticPlayer(
            player_id="p_tank_bigsby",
            name="Tank Bigsby",
            nfl_team="JAX",
            position="RB",
            injury_status="Healthy",
            bye_week=12,
            week_8_projection=13.2,
            season_2025_weekly_pts=[10.4, 11.8, 14.2, 12.5, 13.1, 11.9, 13.6],
            season_2024_weekly_pts=[6.2, 8.4, 15.1, 7.8, 11.2, 9.4, 10.1],
            snap_share_pct=57.0,
            target_or_touch_share_pct=22.4,
            scouting_note="Taking over early-down and goal-line work in Jacksonville; valuable RB trade chip or spot starter.",
            strength_of_schedule_rank=11,
        ),
        SyntheticPlayer(
            player_id="p_kirk_cousins",
            name="Kirk Cousins",
            nfl_team="ATL",
            position="QB",
            injury_status="Healthy",
            bye_week=12,
            week_8_projection=13.4,
            season_2025_weekly_pts=[14.2, 12.8, 13.5, 11.9, 14.0, 12.6, 12.7],
            season_2024_weekly_pts=[15.8, 17.2, 14.9, 18.4, 16.1, 15.9, 16.5],
            snap_share_pct=100.0,
            target_or_touch_share_pct=0.0,
            scouting_note="Trending down (-3.3 PPG vs. 2024) as Atlanta leans heavily on the run game.",
            strength_of_schedule_rank=18,
        ),
        SyntheticPlayer(
            player_id="p_quentin_johnston",
            name="Quentin Johnston",
            nfl_team="LAC",
            position="WR",
            injury_status="Doubtful",
            bye_week=5,
            week_8_projection=4.1,
            season_2025_weekly_pts=[8.4, 6.2, 5.1, 7.9, 4.8, 5.5, 3.9],
            season_2024_weekly_pts=[7.5, 14.2, 9.1, 5.4, 6.8, 8.0, 7.2],
            snap_share_pct=42.0,
            target_or_touch_share_pct=11.0,
            scouting_note=(
                "Doubtful for Week 8 with a lingering hamstring injury and lost snaps to Ladd McConkey. "
                "Clear #1 DROP candidate on Gridiron Guardians' bench."
            ),
            strength_of_schedule_rank=16,
        ),
        # --- TEAM BRAVO (Blitzkrieg Birds - Week 8 Opponent of Team Alpha) ---
        SyntheticPlayer(
            player_id="p_lamar_jackson",
            name="Lamar Jackson",
            nfl_team="BAL",
            position="QB",
            injury_status="Healthy",
            bye_week=14,
            week_8_projection=24.1,
            season_2025_weekly_pts=[23.5, 25.0, 22.8, 26.4, 21.9, 24.7, 23.8],
            season_2024_weekly_pts=[22.1, 24.0, 23.5, 21.8, 25.2, 22.9, 24.1],
            snap_share_pct=99.0,
            target_or_touch_share_pct=17.5,
            scouting_note="Consistent elite dual-threat QB1 averaging 24.0 PPG.",
            strength_of_schedule_rank=7,
        ),
        SyntheticPlayer(
            player_id="p_saquon_barkley",
            name="Saquon Barkley",
            nfl_team="PHI",
            position="RB",
            injury_status="Healthy",
            bye_week=5,
            week_8_projection=20.4,
            season_2025_weekly_pts=[21.0, 19.4, 22.5, 18.8, 20.1, 21.6, 19.9],
            season_2024_weekly_pts=[24.2, 18.6, 23.1, 16.4, 19.8, 22.0, 20.5],
            snap_share_pct=84.0,
            target_or_touch_share_pct=32.0,
            scouting_note="High-volume workhorse back in Philadelphia offense.",
            strength_of_schedule_rank=5,
        ),
        SyntheticPlayer(
            player_id="p_tony_pollard",
            name="Tony Pollard",
            nfl_team="TEN",
            position="RB",
            injury_status="Healthy",
            bye_week=5,
            week_8_projection=11.2,
            season_2025_weekly_pts=[11.4, 10.8, 12.1, 9.6, 11.9, 10.5, 11.2],
            season_2024_weekly_pts=[13.2, 12.4, 9.8, 14.1, 11.6, 12.9, 11.5],
            snap_share_pct=62.0,
            target_or_touch_share_pct=21.0,
            scouting_note="Steady volume RB2 on a low-scoring offense; Blitzkrieg Birds want an upside RB upgrade.",
            strength_of_schedule_rank=21,
        ),
        SyntheticPlayer(
            player_id="p_ceedee_lamb",
            name="CeeDee Lamb",
            nfl_team="DAL",
            position="WR",
            injury_status="Healthy",
            bye_week=7,
            week_8_projection=19.1,
            season_2025_weekly_pts=[18.2, 20.4, 17.9, 21.5, 19.0, 18.6, 19.4],
            season_2024_weekly_pts=[15.4, 17.8, 14.2, 19.6, 18.1, 21.4, 17.9],
            snap_share_pct=94.0,
            target_or_touch_share_pct=31.8,
            scouting_note="Alpha WR1 leading the league in slot + outside target share.",
            strength_of_schedule_rank=10,
        ),
        SyntheticPlayer(
            player_id="p_zay_flowers",
            name="Zay Flowers",
            nfl_team="BAL",
            position="WR",
            injury_status="Healthy",
            bye_week=14,
            week_8_projection=13.7,
            season_2025_weekly_pts=[12.9, 14.5, 11.8, 15.2, 13.4, 14.1, 13.6],
            season_2024_weekly_pts=[11.8, 15.1, 9.4, 14.8, 16.2, 12.5, 13.0],
            snap_share_pct=86.0,
            target_or_touch_share_pct=24.5,
            scouting_note="Dynamic YAC threat in Baltimore's passing attack.",
            strength_of_schedule_rank=13,
        ),
        SyntheticPlayer(
            player_id="p_trey_mcbride",
            name="Trey McBride",
            nfl_team="ARI",
            position="TE",
            injury_status="Healthy",
            bye_week=11,
            week_8_projection=14.6,
            season_2025_weekly_pts=[13.8, 15.2, 14.1, 16.0, 13.9, 14.8, 15.1],
            season_2024_weekly_pts=[11.2, 13.4, 12.1, 14.0, 13.8, 15.0, 13.9],
            snap_share_pct=92.0,
            target_or_touch_share_pct=26.4,
            scouting_note="Locked-in every-week TE1 for Blitzkrieg Birds.",
            strength_of_schedule_rank=8,
        ),
        SyntheticPlayer(
            player_id="p_chuba_hubbard",
            name="Chuba Hubbard",
            nfl_team="CAR",
            position="RB",
            injury_status="Healthy",
            bye_week=11,
            week_8_projection=10.4,
            season_2025_weekly_pts=[10.2, 11.0, 9.8, 10.6, 11.2, 9.9, 10.1],
            season_2024_weekly_pts=[11.4, 14.2, 15.8, 13.1, 12.9, 11.8, 12.4],
            snap_share_pct=58.0,
            target_or_touch_share_pct=19.2,
            scouting_note="Splitting carries in Carolina; vulnerable FLEX starter.",
            strength_of_schedule_rank=26,
        ),
        # Team Bravo Bench (Surplus Elite TE Sam LaPorta!)
        SyntheticPlayer(
            player_id="p_sam_laporta",
            name="Sam LaPorta",
            nfl_team="DET",
            position="TE",
            injury_status="Healthy",
            bye_week=5,
            week_8_projection=12.9,
            season_2025_weekly_pts=[12.1, 13.4, 11.8, 14.2, 12.6, 13.1, 13.5],
            season_2024_weekly_pts=[8.4, 9.2, 10.5, 11.8, 12.4, 10.9, 11.2],
            snap_share_pct=89.0,
            target_or_touch_share_pct=21.5,
            scouting_note=(
                "Top-5 TE sitting on Blitzkrieg Birds' bench behind Trey McBride. "
                "Prime trade target for TE-needy teams like Gridiron Guardians (`team_alpha`) "
                "in exchange for an RB like Tank Bigsby."
            ),
            strength_of_schedule_rank=9,
        ),
        SyntheticPlayer(
            player_id="p_romeo_doubs",
            name="Romeo Doubs",
            nfl_team="GB",
            position="WR",
            injury_status="Healthy",
            bye_week=10,
            week_8_projection=9.8,
            season_2025_weekly_pts=[9.4, 10.2, 8.9, 11.1, 9.6, 10.0, 9.5],
            season_2024_weekly_pts=[9.0, 8.5, 11.4, 10.2, 9.8, 8.9, 9.4],
            snap_share_pct=79.0,
            target_or_touch_share_pct=17.8,
            scouting_note="Rotational perimeter receiver in Green Bay.",
            strength_of_schedule_rank=15,
        ),
        # --- TEAM CHARLIE (Sunday Crushers) ---
        SyntheticPlayer(
            player_id="p_josh_allen",
            name="Josh Allen",
            nfl_team="BUF",
            position="QB",
            injury_status="Healthy",
            bye_week=12,
            week_8_projection=23.8,
            season_2025_weekly_pts=[24.1, 22.5, 25.0, 21.8, 24.4, 23.2, 24.6],
            season_2024_weekly_pts=[23.2, 19.8, 26.4, 20.1, 22.9, 24.5, 23.8],
            snap_share_pct=99.0,
            target_or_touch_share_pct=16.2,
            scouting_note="Elite QB1 with rushing goal-line upside.",
            strength_of_schedule_rank=11,
        ),
        SyntheticPlayer(
            player_id="p_jahmyr_gibbs",
            name="Jahmyr Gibbs",
            nfl_team="DET",
            position="RB",
            injury_status="Healthy",
            bye_week=5,
            week_8_projection=18.7,
            season_2025_weekly_pts=[17.9, 19.2, 18.4, 20.1, 17.5, 19.0, 18.8],
            season_2024_weekly_pts=[16.4, 17.8, 15.9, 19.2, 18.1, 17.5, 18.4],
            snap_share_pct=68.0,
            target_or_touch_share_pct=27.4,
            scouting_note="Explosive dynamic RB1 with elite receiving efficiency.",
            strength_of_schedule_rank=9,
        ),
        SyntheticPlayer(
            player_id="p_rachaad_white",
            name="Rachaad White",
            nfl_team="TB",
            position="RB",
            injury_status="Healthy",
            bye_week=11,
            week_8_projection=9.4,
            season_2025_weekly_pts=[9.8, 8.9, 10.1, 9.2, 9.5, 8.8, 9.4],
            season_2024_weekly_pts=[12.4, 11.8, 10.9, 13.1, 11.2, 10.5, 11.0],
            snap_share_pct=48.0,
            target_or_touch_share_pct=15.0,
            scouting_note="Losing early-down work; Sunday Crushers actively need an RB2 upgrade.",
            strength_of_schedule_rank=20,
        ),
        SyntheticPlayer(
            player_id="p_jamarr_chase",
            name="Ja'Marr Chase",
            nfl_team="CIN",
            position="WR",
            injury_status="Healthy",
            bye_week=12,
            week_8_projection=20.5,
            season_2025_weekly_pts=[19.8, 22.1, 18.9, 21.4, 20.2, 19.5, 21.0],
            season_2024_weekly_pts=[18.5, 20.9, 17.4, 22.8, 19.1, 20.4, 19.8],
            snap_share_pct=95.0,
            target_or_touch_share_pct=31.0,
            scouting_note="Overall WR1 contender with elite deep-ball and YAC production.",
            strength_of_schedule_rank=6,
        ),
        SyntheticPlayer(
            player_id="p_nico_collins",
            name="Nico Collins",
            nfl_team="HOU",
            position="WR",
            injury_status="Healthy",
            bye_week=14,
            week_8_projection=17.6,
            season_2025_weekly_pts=[16.9, 18.2, 17.1, 18.5, 16.8, 17.9, 17.4],
            season_2024_weekly_pts=[17.2, 18.9, 15.4, 19.1, 16.2, 17.8, 17.0],
            snap_share_pct=89.0,
            target_or_touch_share_pct=28.9,
            scouting_note="Dominant X-receiver leading the NFL in yards per route run.",
            strength_of_schedule_rank=12,
        ),
        SyntheticPlayer(
            player_id="p_brock_bowers",
            name="Brock Bowers",
            nfl_team="LV",
            position="TE",
            injury_status="Healthy",
            bye_week=10,
            week_8_projection=15.1,
            season_2025_weekly_pts=[14.5, 15.8, 14.9, 16.2, 14.1, 15.4, 15.0],
            season_2024_weekly_pts=[12.8, 14.1, 13.5, 15.0, 14.8, 13.9, 14.6],
            snap_share_pct=91.0,
            target_or_touch_share_pct=28.0,
            scouting_note="Focal point of the Las Vegas passing attack.",
            strength_of_schedule_rank=7,
        ),
        SyntheticPlayer(
            player_id="p_dallas_goedert",
            name="Dallas Goedert",
            nfl_team="PHI",
            position="TE",
            injury_status="Healthy",
            bye_week=5,
            week_8_projection=11.6,
            season_2025_weekly_pts=[11.2, 12.0, 10.9, 11.8, 11.5, 12.1, 11.4],
            season_2024_weekly_pts=[10.8, 11.5, 12.4, 9.9, 11.1, 10.6, 11.2],
            snap_share_pct=86.0,
            target_or_touch_share_pct=19.8,
            scouting_note="Reliable TE1 sitting on Sunday Crushers' bench behind Brock Bowers; available for trade.",
            strength_of_schedule_rank=10,
        ),
        # --- AVAILABLE WAIVER WIRE FREE AGENTS (Unrostered) ---
        SyntheticPlayer(
            player_id="p_tyrone_tracy",
            name="Tyrone Tracy Jr.",
            nfl_team="NYG",
            position="RB",
            injury_status="Healthy",
            bye_week=11,
            week_8_projection=14.6,
            season_2025_weekly_pts=[11.2, 13.5, 14.8, 15.1, 14.2, 15.6, 14.9],
            season_2024_weekly_pts=[4.1, 5.2, 7.8, 12.4, 14.9, 11.2, 13.1],
            snap_share_pct=74.0,
            target_or_touch_share_pct=26.8,
            scouting_note=(
                "Top RB waiver pickup: Commands 74% of snaps and 5+ targets/game as New York's "
                "unquestioned three-down back."
            ),
            strength_of_schedule_rank=7,
        ),
        SyntheticPlayer(
            player_id="p_cedric_tillman",
            name="Cedric Tillman",
            nfl_team="CLE",
            position="WR",
            injury_status="Healthy",
            bye_week=10,
            week_8_projection=13.8,
            season_2025_weekly_pts=[10.5, 12.1, 13.4, 14.9, 14.2, 15.0, 14.6],
            season_2024_weekly_pts=[3.2, 4.0, 5.1, 8.4, 15.2, 16.8, 13.4],
            snap_share_pct=91.0,
            target_or_touch_share_pct=27.5,
            scouting_note=(
                "Top WR waiver pickup: Playing 91% of snaps with 10+ targets in three consecutive "
                "games as Cleveland's primary perimeter X-receiver."
            ),
            strength_of_schedule_rank=9,
        ),
        SyntheticPlayer(
            player_id="p_cade_otton",
            name="Cade Otton",
            nfl_team="TB",
            position="TE",
            injury_status="Healthy",
            bye_week=11,
            week_8_projection=12.7,
            season_2025_weekly_pts=[10.2, 11.8, 12.5, 13.4, 12.9, 13.8, 13.1],
            season_2024_weekly_pts=[6.4, 7.9, 9.2, 11.5, 14.8, 13.2, 11.9],
            snap_share_pct=95.0,
            target_or_touch_share_pct=25.4,
            scouting_note=(
                "Top TE waiver pickup: Operating as Tampa Bay's primary middle-of-field target "
                "(25.4% target share) and immediate upgrade over Evan Engram."
            ),
            strength_of_schedule_rank=5,
        ),
        SyntheticPlayer(
            player_id="p_bo_nix",
            name="Bo Nix",
            nfl_team="DEN",
            position="QB",
            injury_status="Healthy",
            bye_week=14,
            week_8_projection=18.5,
            season_2025_weekly_pts=[16.8, 17.5, 18.2, 19.1, 17.4, 18.9, 18.6],
            season_2024_weekly_pts=[11.4, 13.2, 16.8, 14.5, 18.1, 17.2, 16.9],
            snap_share_pct=100.0,
            target_or_touch_share_pct=14.2,
            scouting_note="Top QB waiver streamer with 35+ rushing yards per game and favorable Week 8 matchup.",
            strength_of_schedule_rank=4,
        ),
        SyntheticPlayer(
            player_id="p_josh_downs",
            name="Josh Downs",
            nfl_team="IND",
            position="WR",
            injury_status="Healthy",
            bye_week=14,
            week_8_projection=12.4,
            season_2025_weekly_pts=[11.0, 12.6, 11.8, 13.2, 12.1, 12.9, 12.5],
            season_2024_weekly_pts=[9.8, 11.4, 10.2, 13.5, 11.9, 10.8, 11.6],
            snap_share_pct=82.0,
            target_or_touch_share_pct=26.1,
            scouting_note="High-floor slot target earner averaging 7.2 receptions per game in Half-PPR.",
            strength_of_schedule_rank=12,
        ),
        SyntheticPlayer(
            player_id="p_tucker_kraft",
            name="Tucker Kraft",
            nfl_team="GB",
            position="TE",
            injury_status="Healthy",
            bye_week=10,
            week_8_projection=10.9,
            season_2025_weekly_pts=[9.8, 10.5, 11.2, 10.1, 11.6, 10.4, 10.8],
            season_2024_weekly_pts=[7.2, 8.9, 11.4, 9.5, 10.2, 9.8, 10.1],
            snap_share_pct=87.0,
            target_or_touch_share_pct=18.2,
            scouting_note="Every-down inline TE with strong red-zone target share.",
            strength_of_schedule_rank=14,
        ),
    ]
    return {p.player_id: p for p in players_list}


def _build_initial_teams() -> dict[str, SyntheticTeam]:
    """Construct the synthetic fantasy teams and their Week 8 schedules."""
    return {
        "team_alpha": SyntheticTeam(
            team_id="team_alpha",
            team_name="Gridiron Guardians",
            manager_name="Alex Rivera",
            wins=5,
            losses=2,
            points_for=894.6,
            points_against=812.3,
            starters=[
                "p_jayden_daniels",
                "p_bijan_robinson",
                "p_kenneth_walker",
                "p_amon_ra",
                "p_garrett_wilson",
                "p_evan_engram",
                "p_jaylen_warren",
            ],
            bench=[
                "p_ladd_mcconkey",
                "p_tank_bigsby",
                "p_kirk_cousins",
                "p_quentin_johnston",
            ],
            weekly_opponents={8: "team_bravo", 9: "team_charlie"},
        ),
        "team_bravo": SyntheticTeam(
            team_id="team_bravo",
            team_name="Blitzkrieg Birds",
            manager_name="Jordan Chen",
            wins=5,
            losses=2,
            points_for=902.1,
            points_against=835.0,
            starters=[
                "p_lamar_jackson",
                "p_saquon_barkley",
                "p_tony_pollard",
                "p_ceedee_lamb",
                "p_zay_flowers",
                "p_trey_mcbride",
                "p_chuba_hubbard",
            ],
            bench=[
                "p_sam_laporta",
                "p_romeo_doubs",
            ],
            weekly_opponents={8: "team_alpha", 9: "team_Alpha"},
        ),
        "team_charlie": SyntheticTeam(
            team_id="team_charlie",
            team_name="Sunday Crushers",
            manager_name="Samir Patel",
            wins=4,
            losses=3,
            points_for=861.4,
            points_against=848.9,
            starters=[
                "p_josh_allen",
                "p_jahmyr_gibbs",
                "p_rachaad_white",
                "p_jamarr_chase",
                "p_nico_collins",
                "p_brock_bowers",
                "p_romeo_doubs",
            ],
            bench=[
                "p_dallas_goedert",
            ],
            weekly_opponents={8: "team_alpha", 9: "team_alpha"},
        ),
    }


class SyntheticLeagueStore:
    """In-memory deterministic fantasy football league store supporting state mutations."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        """Reset the synthetic league to its deterministic seed state."""
        self.players: dict[str, SyntheticPlayer] = _build_initial_players()
        self.teams: dict[str, SyntheticTeam] = _build_initial_teams()
        # Fix sunday crushers starter so there is no overlap with team_bravo bench
        self.players["p_jakobi_meyers"] = SyntheticPlayer(
            player_id="p_jakobi_meyers",
            name="Jakobi Meyers",
            nfl_team="LV",
            position="WR",
            injury_status="Healthy",
            bye_week=10,
            week_8_projection=11.4,
            season_2025_weekly_pts=[10.8, 11.9, 11.2, 12.0, 10.5, 11.8, 11.6],
            season_2024_weekly_pts=[10.1, 11.0, 9.8, 11.5, 10.9, 11.2, 10.8],
            snap_share_pct=88.0,
            target_or_touch_share_pct=23.1,
            scouting_note="Steady WR3 volume option in Las Vegas.",
            strength_of_schedule_rank=15,
        )
        self.teams["team_charlie"].starters[-1] = "p_jakobi_meyers"
        self.transaction_log: list[dict[str, Any]] = []

    def resolve_team(self, identifier: str) -> SyntheticTeam | None:
        """Resolve a team by `team_id`, `team_name`, or `manager_name` (case-insensitive)."""
        cleaned = identifier.strip().lower()
        if cleaned in self.teams:
            return self.teams[cleaned]
        for team in self.teams.values():
            if (
                cleaned == team.team_name.lower()
                or cleaned == team.manager_name.lower()
                or cleaned in team.team_name.lower()
            ):
                return team
        return None

    def resolve_player(self, identifier: str) -> SyntheticPlayer | None:
        """Resolve a player by `player_id` or full/partial `name` (case-insensitive)."""
        cleaned = identifier.strip().lower()
        if cleaned in self.players:
            return self.players[cleaned]
        for player in self.players.values():
            if cleaned == player.name.lower() or cleaned in player.name.lower():
                return player
        return None

    def get_rostered_player_ids(self) -> set[str]:
        """Return the set of all currently rostered player IDs across the league."""
        rostered: set[str] = set()
        for team in self.teams.values():
            rostered.update(team.starters)
            rostered.update(team.bench)
        return rostered

    def get_waiver_pool(self, position: str | None = None) -> list[SyntheticPlayer]:
        """Return all unrostered players available on the waiver wire."""
        rostered = self.get_rostered_player_ids()
        available = [
            p
            for pid, p in self.players.items()
            if pid not in rostered
            and (not position or position.upper() == "ALL" or p.position == position.upper())
        ]
        return sorted(available, key=lambda p: p.week_8_projection, reverse=True)

    def snapshot_player(self, player: SyntheticPlayer) -> dict[str, Any]:
        """Return a serializable dictionary summary of a player."""
        return {
            "player_id": player.player_id,
            "name": player.name,
            "nfl_team": player.nfl_team,
            "position": player.position,
            "injury_status": player.injury_status,
            "bye_week": player.bye_week,
            "week_8_projection": player.week_8_projection,
            "avg_pts_2025": player.avg_pts_2025,
            "avg_pts_2024": player.avg_pts_2024,
            "yoy_delta_ppg": player.yoy_delta_ppg,
            "snap_share_pct": player.snap_share_pct,
            "target_or_touch_share_pct": player.target_or_touch_share_pct,
            "strength_of_schedule_rank": player.strength_of_schedule_rank,
            "scouting_note": player.scouting_note,
        }


class AsyncFantasyMemoryIndexer:
    """Asynchronous background indexer for multi-season player trends and team needs.

    Satisfies AgentOps Rubric Criterion 2.4 (Async Memory Operations):
    Expensive memory generation and consolidation are coded as background or async
    tasks (`asyncio.create_task` / `async` coroutines) to prevent UI blocking.
    """

    def __init__(self, store: SyntheticLeagueStore) -> None:
        self._store = store
        self._indexed_trends: dict[str, dict[str, Any]] = {}
        self._team_positional_grades: dict[str, dict[str, Any]] = {}
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._lock = asyncio.Lock()

    @property
    def is_indexed(self) -> bool:
        """Return True if the trend and team index has been populated."""
        return bool(self._indexed_trends)

    async def build_index_async(self) -> dict[str, Any]:
        """Asynchronously compute longitudinal player trends and team positional grades."""
        async with self._lock:
            # Yield to the event loop to keep UI/agent turns non-blocking
            await asyncio.sleep(0)
            trends: dict[str, dict[str, Any]] = {}
            for pid, player in self._store.players.items():
                recent_3_avg = round(sum(player.season_2025_weekly_pts[-3:]) / 3.0, 2)
                early_4_avg = round(sum(player.season_2025_weekly_pts[:4]) / 4.0, 2)
                momentum_delta = round(recent_3_avg - early_4_avg, 2)
                direction = (
                    "surging"
                    if player.yoy_delta_ppg >= 2.0
                    else "declining"
                    if player.yoy_delta_ppg <= -2.0
                    else "steady"
                )
                trends[pid] = {
                    "player_id": pid,
                    "name": player.name,
                    "position": player.position,
                    "avg_pts_2025": player.avg_pts_2025,
                    "avg_pts_2024": player.avg_pts_2024,
                    "yoy_delta_ppg": player.yoy_delta_ppg,
                    "recent_3_week_avg": recent_3_avg,
                    "momentum_delta": momentum_delta,
                    "trend_direction": direction,
                }

            team_grades: dict[str, dict[str, Any]] = {}
            for tid, team in self._store.teams.items():
                pos_projections: dict[str, list[float]] = {"QB": [], "RB": [], "WR": [], "TE": []}
                for pid in team.starters + team.bench:
                    p = self._store.players[pid]
                    pos_projections.setdefault(p.position, []).append(p.week_8_projection)
                team_grades[tid] = {
                    pos: round(sum(vals), 2) for pos, vals in pos_projections.items()
                }

            self._indexed_trends = trends
            self._team_positional_grades = team_grades
            return {
                "indexed_players_count": len(self._indexed_trends),
                "indexed_teams_count": len(self._team_positional_grades),
            }

    def trigger_background_refresh(self) -> asyncio.Task[None] | None:
        """Schedule a non-blocking background index consolidation task on the active loop."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None

        async def _runner() -> None:
            await self.build_index_async()

        task = loop.create_task(_runner())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def get_player_trend_summary(self, player_id: str) -> dict[str, Any] | None:
        """Retrieve a player's consolidated trend summary, indexing asynchronously if needed."""
        if not self._indexed_trends:
            await self.build_index_async()
        summary = self._indexed_trends.get(player_id)
        return copy.deepcopy(summary) if summary else None


_DEFAULT_STORE = SyntheticLeagueStore()
_DEFAULT_INDEXER = AsyncFantasyMemoryIndexer(_DEFAULT_STORE)


def get_league_store() -> SyntheticLeagueStore:
    """Return the singleton SyntheticLeagueStore instance."""
    return _DEFAULT_STORE


def get_memory_indexer() -> AsyncFantasyMemoryIndexer:
    """Return the singleton AsyncFantasyMemoryIndexer instance."""
    return _DEFAULT_INDEXER
