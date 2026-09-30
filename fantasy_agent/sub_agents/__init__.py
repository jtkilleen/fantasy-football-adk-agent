"""Specialized ADK sub-agents for the Fantasy Football Personal Agent."""

from fantasy_agent.sub_agents.analytics_trend_agent import build_analytics_trend_agent
from fantasy_agent.sub_agents.league_roster_agent import build_league_roster_agent
from fantasy_agent.sub_agents.trade_strategy_agent import build_trade_strategy_agent

__all__ = [
    "build_analytics_trend_agent",
    "build_league_roster_agent",
    "build_trade_strategy_agent",
]
