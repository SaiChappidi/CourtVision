"""NBA proxy API routes."""

from typing import Any

from fastapi import APIRouter, Query

from app.config import settings
from app.gateway.proxy import nba_proxy

DEFAULT_SEASON = settings.default_season

router = APIRouter(prefix="/nba", tags=["NBA Gateway"])


@router.get("/teams")
async def list_teams() -> list[dict[str, Any]]:
    return await nba_proxy.get_teams()


@router.get("/roster/{team_abbr}")
async def get_roster(
    team_abbr: str,
    season: str = Query(default=DEFAULT_SEASON),
) -> dict[str, Any]:
    return await nba_proxy.get_full_roster(team_abbr, season)


@router.get("/standings")
async def get_standings(season: str = Query(default=DEFAULT_SEASON)) -> dict[str, Any]:
    return await nba_proxy.route("standings", season=season)


@router.get("/player-stats")
async def get_player_stats(season: str = Query(default=DEFAULT_SEASON)) -> dict[str, Any]:
    return await nba_proxy.route("player_stats", season=season)


@router.get("/team-stats")
async def get_team_stats(season: str = Query(default=DEFAULT_SEASON)) -> dict[str, Any]:
    return await nba_proxy.route("team_stats", season=season)


@router.get("/search/{player_name}")
async def search_player(player_name: str) -> list[dict[str, Any]]:
    from app.gateway.nba_client import nba_client
    return await nba_client.search_player(player_name)
