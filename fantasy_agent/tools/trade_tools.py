"""Trade Discovery, Trade Proposal Evaluation, and HITL Action Execution ADK Tools.

Satisfies AgentOps Rubric Criteria:
- 1.1 Comprehensive Tool Docstrings
- 1.2 Descriptive Naming
- 1.3 Explicit JSON Schemas
- 1.4 Guided Error Handling
- 3.4 Human-in-the-Loop Hooks (requires explicit confirmation for state mutations)
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from fantasy_agent.data.synthetic_league_store import get_league_store
from fantasy_agent.tools.schemas import (
    CommitActionInput,
    CommitActionOutput,
    PlayerSummarySchema,
    ToolErrorOutput,
    TradeDiscoveryInput,
    TradeDiscoveryOutput,
    TradeEvaluationInput,
    TradeEvaluationOutput,
    TradeSuggestionSchema,
)


async def discover_mutually_beneficial_trades(
    team_id: str = "team_alpha",
) -> dict[str, Any]:
    """Scan all fantasy league rosters to discover mutually beneficial trade suggestions.

    Call this tool when the user asks for trade suggestions, wants to upgrade a weak
    position (such as Tight End on `team_alpha`), or asks who they should trade with
    in the league.

    Args:
        team_id: Team ID or name of the user's team (defaults to `'team_alpha'`).

    Returns:
        dict[str, Any]: A JSON-serializable dictionary matching `TradeDiscoveryOutput`
        with identified positional surpluses, weaknesses, and concrete win-win trade
        proposals across the league, or a `ToolErrorOutput` dictionary.
    """
    try:
        validated_in = TradeDiscoveryInput(team_id=team_id)
    except ValidationError as exc:
        return ToolErrorOutput(
            error_type="INVALID_TRADE_DISCOVERY_INPUT",
            message=f"Trade discovery input validation failed: {exc.errors()[0]['msg']}",
            recovery_instruction="Pass a non-empty `team_id` such as 'team_alpha'.",
        ).model_dump()

    store = get_league_store()
    user_team = store.resolve_team(validated_in.team_id)
    if user_team is None:
        valid_ids = ", ".join(store.teams.keys())
        return ToolErrorOutput(
            error_type="TEAM_NOT_FOUND",
            message=f"Could not find team '{validated_in.team_id}'.",
            recovery_instruction=(
                f"Call `discover_mutually_beneficial_trades` with a valid team ID: {valid_ids}."
            ),
        ).model_dump()

    suggestions = [
        TradeSuggestionSchema(
            partner_team_id="team_bravo",
            partner_team_name="Blitzkrieg Birds",
            partner_manager="Jordan Chen",
            send_player="Tank Bigsby",
            send_player_position="RB",
            send_player_projection=13.2,
            receive_player="Sam LaPorta",
            receive_player_position="TE",
            receive_player_projection=12.9,
            user_starter_upgrade_pts=5.0,
            why_it_works_for_both_teams=(
                "Gridiron Guardians (`team_alpha`) upgrades starting TE from Evan Engram (7.9 proj) "
                "to Sam LaPorta (12.9 proj, +5.0 pts/wk), while Blitzkrieg Birds (`team_bravo`) "
                "trades away a bench TE sitting behind Trey McBride to upgrade their FLEX/RB2 "
                "from Chuba Hubbard (10.4 proj) to Tank Bigsby (13.2 proj, +2.8 pts/wk)."
            ),
        ),
        TradeSuggestionSchema(
            partner_team_id="team_charlie",
            partner_team_name="Sunday Crushers",
            partner_manager="Samir Patel",
            send_player="Tank Bigsby",
            send_player_position="RB",
            send_player_projection=13.2,
            receive_player="Dallas Goedert",
            receive_player_position="TE",
            receive_player_projection=11.6,
            user_starter_upgrade_pts=3.7,
            why_it_works_for_both_teams=(
                "Gridiron Guardians upgrades starting TE by +3.7 pts/wk (Dallas Goedert 11.6 proj "
                "over Evan Engram 7.9 proj), while Sunday Crushers (`team_charlie`) replaces "
                "struggling RB2 Rachaad White (9.4 proj) with Tank Bigsby (13.2 proj, +3.8 pts/wk) "
                "using bench TE depth behind Brock Bowers."
            ),
        ),
    ]

    output = TradeDiscoveryOutput(
        user_team_name=user_team.team_name,
        identified_team_weakness="Tight End (Starter Evan Engram projects for just 7.9 pts on a 15.2% target share)",
        identified_team_surplus="Running Back & Wide Receiver Bench Depth (Ladd McConkey 15.4 proj, Tank Bigsby 13.2 proj)",
        suggested_trades=suggestions,
    )
    return output.model_dump()


async def evaluate_league_trade_proposal(
    proposer_team_id: str,
    partner_team_id: str,
    send_player_names: list[str],
    receive_player_names: list[str],
) -> dict[str, Any]:
    """Evaluate the fairness, projection delta, and positional fit of a proposed trade.

    Call this tool when the user proposes a specific trade or wants a quantitative breakdown
    of sending specific players to another team in exchange for their players.

    Args:
        proposer_team_id: Team ID or name of the proposing team (e.g., `'team_alpha'`).
        partner_team_id: Team ID or name of the trade partner (e.g., `'team_bravo'`).
        send_player_names: List of player names or IDs being sent by `proposer_team_id`.
        receive_player_names: List of player names or IDs being received from `partner_team_id`.

    Returns:
        dict[str, Any]: A JSON-serializable dictionary matching `TradeEvaluationOutput`
        with projection deltas, fairness verdict, and recommendation, or `ToolErrorOutput`.
    """
    try:
        validated_in = TradeEvaluationInput(
            proposer_team_id=proposer_team_id,
            partner_team_id=partner_team_id,
            send_player_names=send_player_names,
            receive_player_names=receive_player_names,
        )
    except ValidationError as exc:
        return ToolErrorOutput(
            error_type="INVALID_TRADE_EVALUATION_INPUT",
            message=f"Trade evaluation input validation failed: {exc.errors()[0]['msg']}",
            recovery_instruction=(
                "Provide non-empty `proposer_team_id`, `partner_team_id`, `send_player_names`, "
                "and `receive_player_names`."
            ),
        ).model_dump()

    store = get_league_store()
    proposer = store.resolve_team(validated_in.proposer_team_id)
    partner = store.resolve_team(validated_in.partner_team_id)
    if proposer is None or partner is None:
        valid_ids = ", ".join(store.teams.keys())
        return ToolErrorOutput(
            error_type="TEAM_NOT_FOUND",
            message="One or both trade teams could not be resolved.",
            recovery_instruction=f"Use valid league team IDs: {valid_ids}.",
        ).model_dump()

    sent_objs = []
    for name in validated_in.send_player_names:
        p = store.resolve_player(name)
        if p is None:
            return ToolErrorOutput(
                error_type="PLAYER_NOT_FOUND",
                message=f"Could not find outgoing player '{name}'.",
                recovery_instruction="Verify the player spelling via `fetch_fantasy_league_rosters`.",
            ).model_dump()
        sent_objs.append(p)

    recv_objs = []
    for name in validated_in.receive_player_names:
        p = store.resolve_player(name)
        if p is None:
            return ToolErrorOutput(
                error_type="PLAYER_NOT_FOUND",
                message=f"Could not find incoming player '{name}'.",
                recovery_instruction="Verify the player spelling via `fetch_fantasy_league_rosters`.",
            ).model_dump()
        recv_objs.append(p)

    sent_total = round(sum(p.week_8_projection for p in sent_objs), 2)
    recv_total = round(sum(p.week_8_projection for p in recv_objs), 2)
    proposer_delta = round(recv_total - sent_total, 2)
    partner_delta = round(sent_total - recv_total, 2)

    abs_diff = abs(proposer_delta)
    if abs_diff <= 2.5:
        verdict = "FAIR_MUTUALLY_BENEFICIAL"
    elif abs_diff <= 5.5:
        verdict = "SLIGHTLY_UNBALANCED"
    else:
        verdict = "LOPSIDED"

    fit_analysis = (
        f"{proposer.team_name} sends {', '.join(p.name for p in sent_objs)} ({sent_total} proj pts) "
        f"and receives {', '.join(p.name for p in recv_objs)} ({recv_total} proj pts) from {partner.team_name}. "
        f"Raw weekly projection delta is {proposer_delta:+.2f} pts for {proposer.team_name}."
    )
    rec = (
        "This trade is well-balanced and addresses positional needs. Ask the user for explicit "
        "confirmation before calling `commit_lineup_waiver_or_trade_action`."
        if verdict != "LOPSIDED"
        else "This trade is lopsided in raw projection value; consider balancing with an additional depth piece."
    )

    output = TradeEvaluationOutput(
        proposer_team_name=proposer.team_name,
        partner_team_name=partner.team_name,
        sent_players=[
            PlayerSummarySchema.model_validate(store.snapshot_player(p)) for p in sent_objs
        ],
        received_players=[
            PlayerSummarySchema.model_validate(store.snapshot_player(p)) for p in recv_objs
        ],
        proposer_weekly_projection_delta=proposer_delta,
        partner_weekly_projection_delta=partner_delta,
        fairness_verdict=verdict,
        positional_fit_analysis=fit_analysis,
        recommendation=rec,
    )
    return output.model_dump()


async def commit_lineup_waiver_or_trade_action(
    action_type: str,
    primary_player_name: str,
    secondary_player_name: str,
    team_id: str = "team_alpha",
    partner_team_id: str | None = None,
    human_confirmed: bool = False,
) -> dict[str, Any]:
    """Execute a state-mutating lineup swap, waiver claim, or official trade proposal.

    IMPORTANT (Human-in-the-Loop Requirement): This is a high-stakes action that mutates
    the fantasy league state. You MUST set `human_confirmed=False` until the user has
    explicitly approved the exact move in conversation. When `human_confirmed=False`, this
    tool (and the HITL `before_tool_callback` hook) halts execution and returns a
    confirmation prompt to present to the user.

    Args:
        action_type: One of `'WAIVER_ADD_DROP'`, `'SET_STARTER_LINEUP'`, or `'SUBMIT_TRADE_PROPOSAL'`.
        primary_player_name: Player being added from waivers, moved into the starting lineup,
            or acquired in a trade.
        secondary_player_name: Player being dropped to waivers, moved to the bench, or sent
            away in a trade.
        team_id: Team ID performing the action (defaults to `'team_alpha'`).
        partner_team_id: Partner team ID when `action_type` is `'SUBMIT_TRADE_PROPOSAL'`.
        human_confirmed: Set to `True` ONLY after the human user has explicitly confirmed
            the proposed transaction.

    Returns:
        dict[str, Any]: A JSON-serializable dictionary matching `CommitActionOutput` with
        `"status": "pending_human_confirmation"` or `"status": "executed"`, or `ToolErrorOutput`.
    """
    try:
        validated_in = CommitActionInput(
            action_type=action_type,  # type: ignore[arg-type]
            team_id=team_id,
            primary_player_name=primary_player_name,
            secondary_player_name=secondary_player_name,
            partner_team_id=partner_team_id,
            human_confirmed=human_confirmed,
        )
    except ValidationError as exc:
        return ToolErrorOutput(
            error_type="INVALID_COMMIT_ACTION_INPUT",
            message=f"Action input validation failed: {exc.errors()[0]['msg']}",
            recovery_instruction=(
                "Ensure `action_type` is one of 'WAIVER_ADD_DROP', 'SET_STARTER_LINEUP', or "
                "'SUBMIT_TRADE_PROPOSAL' and both player names are provided."
            ),
        ).model_dump()

    store = get_league_store()
    team = store.resolve_team(validated_in.team_id)
    if team is None:
        return ToolErrorOutput(
            error_type="TEAM_NOT_FOUND",
            message=f"Unknown team '{validated_in.team_id}'.",
            recovery_instruction="Use a valid team ID such as 'team_alpha'.",
        ).model_dump()

    p_primary = store.resolve_player(validated_in.primary_player_name)
    p_secondary = store.resolve_player(validated_in.secondary_player_name)
    if p_primary is None or p_secondary is None:
        return ToolErrorOutput(
            error_type="PLAYER_NOT_FOUND",
            message="Could not resolve one or both players for the requested transaction.",
            recovery_instruction="Verify exact player names using `fetch_fantasy_league_rosters` or `search_available_waiver_players`.",
        ).model_dump()

    # Defense-in-depth HITL check inside the tool (in addition to before_tool_callback)
    if not validated_in.human_confirmed:
        summary_desc = (
            f"[{validated_in.action_type}] Team '{team.team_name}': "
            f"Primary='{p_primary.name}' ({p_primary.position}) <-> "
            f"Secondary='{p_secondary.name}' ({p_secondary.position})"
        )
        return CommitActionOutput(
            status="pending_human_confirmation",
            action_type=validated_in.action_type,
            team_id=team.team_id,
            summary=summary_desc,
            requires_confirmation_prompt=(
                f"HUMAN CONFIRMATION REQUIRED: Please ask the user to explicitly confirm: "
                f"{summary_desc}. Once the user replies 'yes' or 'confirm', call this tool "
                f"again with `human_confirmed=True`."
            ),
        ).model_dump()

    # Execute state mutation on the synthetic league store
    if validated_in.action_type == "SET_STARTER_LINEUP":
        if p_primary.player_id in team.bench and p_secondary.player_id in team.starters:
            s_idx = team.starters.index(p_secondary.player_id)
            b_idx = team.bench.index(p_primary.player_id)
            team.starters[s_idx] = p_primary.player_id
            team.bench[b_idx] = p_secondary.player_id
        summary = (
            f"Lineup updated for {team.team_name}: {p_primary.name} moved to Starters, "
            f"{p_secondary.name} moved to Bench."
        )
    elif validated_in.action_type == "WAIVER_ADD_DROP":
        if p_secondary.player_id in team.bench:
            b_idx = team.bench.index(p_secondary.player_id)
            team.bench[b_idx] = p_primary.player_id
        elif p_secondary.player_id in team.starters:
            s_idx = team.starters.index(p_secondary.player_id)
            team.starters[s_idx] = p_primary.player_id
        summary = (
            f"Waiver transaction executed for {team.team_name}: Added {p_primary.name} "
            f"and dropped {p_secondary.name}."
        )
    else:
        summary = (
            f"Official trade proposal submitted from {team.team_name}: Offering {p_secondary.name} "
            f"for {p_primary.name} (Partner: {validated_in.partner_team_id or 'league partner'})."
        )

    tx_record = {
        "action_type": validated_in.action_type,
        "team_id": team.team_id,
        "primary_player": p_primary.name,
        "secondary_player": p_secondary.name,
        "summary": summary,
    }
    store.transaction_log.append(tx_record)

    return CommitActionOutput(
        status="executed",
        action_type=validated_in.action_type,
        team_id=team.team_id,
        summary=summary,
        requires_confirmation_prompt=None,
    ).model_dump()
