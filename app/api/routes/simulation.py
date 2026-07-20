"""Monte Carlo simulation API routes."""

from fastapi import APIRouter, HTTPException

from app.models.simulation import SimulationRequest, SimulationResult
from app.services.roster_service import roster_service
from app.simulator.monte_carlo import simulator

router = APIRouter(prefix="/simulate", tags=["Simulation"])


@router.post("/season", response_model=SimulationResult)
async def simulate_season(request: SimulationRequest) -> SimulationResult:
    try:
        roster = await roster_service.get_roster(request.team_abbreviation)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await simulator.simulate(roster, request)


@router.get("/season/{team_abbr}", response_model=SimulationResult)
async def simulate_season_quick(
    team_abbr: str,
    iterations: int = 1000,
) -> SimulationResult:
    request = SimulationRequest(team_abbreviation=team_abbr, iterations=iterations)
    roster = await roster_service.get_roster(team_abbr)
    return await simulator.simulate(roster, request)
