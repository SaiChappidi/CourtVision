"""Proxy request routing for NBA API endpoints."""

import logging
from typing import Any

import logging

from fastapi import HTTPException

from app.gateway.nba_client import TEAM_ID_MAP, TEAM_NAME_MAP, nba_client

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)

ROUTE_MAP = {
    "roster": nba_client.get_team_roster,
    "standings": nba_client.get_league_standings,
    "player_stats": nba_client.get_player_stats,
    "team_stats": nba_client.get_team_stats,
}


class NBAProxy:
    """Routes incoming API requests to the appropriate NBA stats endpoint."""

    async def route(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        handler = ROUTE_MAP.get(endpoint)
        if not handler:
            raise HTTPException(status_code=404, detail=f"Unknown NBA endpoint: {endpoint}")

        try:
            return await handler(**kwargs)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ConnectionError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    async def get_teams(self) -> list[dict[str, Any]]:
        return [
            {"abbreviation": abbr, "team_id": tid, "name": TEAM_NAME_MAP.get(abbr, abbr)}
            for abbr, tid in TEAM_ID_MAP.items()
        ]

    async def get_full_roster(self, team_abbr: str, season: str | None = None) -> dict[str, Any]:
        roster_data = await nba_client.get_team_roster(team_abbr, season)
        players_raw = nba_client.parse_roster_response(roster_data, team_abbr)

        stats_map: dict = {}
        try:
            stats_data = await nba_client.get_player_stats(season)
            stats_map = nba_client.parse_player_stats(stats_data)
        except ConnectionError:
            logger.warning("Player stats unavailable — returning roster without enriched stats")

        enriched = []
        for p in players_raw:
            pid = p["player_id"]
            stats = stats_map.get(pid, {})
            enriched.append({**p, **stats})

        return {
            "team_abbreviation": team_abbr.upper(),
            "team_name": TEAM_NAME_MAP.get(team_abbr.upper(), team_abbr),
            "team_id": TEAM_ID_MAP.get(team_abbr.upper()),
            "season": season,
            "players": enriched,
        }


nba_proxy = NBAProxy()
