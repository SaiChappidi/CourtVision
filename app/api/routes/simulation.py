"""Monte Carlo simulation API routes."""

import asyncio

from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.models.simulation import (
    SimulationRequest,
    SimulationResult,
    TeamCompareRequest,
    TeamCompareResult,
)
from app.services.roster_service import roster_service
from app.simulator.monte_carlo import simulator

router = APIRouter(prefix="/simulate", tags=["Simulation"])


@router.post("/season", response_model=SimulationResult)
async def simulate_season(request: SimulationRequest) -> SimulationResult:
    try:
        roster = await roster_service.get_roster(request.team_abbreviation)
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await simulator.simulate(roster, request)


@router.get("/season/{team_abbr}", response_model=SimulationResult)
async def simulate_season_quick(
    team_abbr: str,
    iterations: int = 1000,
    season: str = Query(default=settings.default_season),
) -> SimulationResult:
    try:
        roster = await roster_service.get_roster(team_abbr, season)
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    request = SimulationRequest(team_abbreviation=team_abbr, iterations=iterations)
    return await simulator.simulate(roster, request)


@router.post("/compare", response_model=TeamCompareResult)
async def compare_teams(request: TeamCompareRequest) -> TeamCompareResult:
    season = request.season or settings.default_season
    try:
        roster_a, roster_b = await asyncio.gather(
            roster_service.get_roster(request.team_a, season),
            roster_service.get_roster(request.team_b, season),
        )
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return await simulator.compare_teams(roster_a, roster_b, request)
