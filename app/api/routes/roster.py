"""Roster management API routes."""

from copy import deepcopy

from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.models.roster import RosterChart, RosterUpdatePayload, TradeRequest
from app.models.simulation import ScenarioComparison
from app.services.roster_service import roster_service
from app.simulator.monte_carlo import simulator

router = APIRouter(prefix="/roster", tags=["Roster Management"])


@router.get("/{team_abbr}", response_model=RosterChart)
async def get_team_roster(
    team_abbr: str,
    season: str = Query(default=settings.default_season),
    reload: bool = Query(default=False),
) -> RosterChart:
    try:
        if reload:
            return await roster_service.reload_roster(team_abbr, season)
        return await roster_service.get_roster(team_abbr, season)
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.put("/{team_abbr}", response_model=RosterChart)
async def update_roster(team_abbr: str, payload: RosterUpdatePayload) -> RosterChart:
    payload.team_abbreviation = team_abbr.upper()
    try:
        await roster_service.get_roster(team_abbr)
        return roster_service.update_roster(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{team_abbr}/trade")
async def execute_trade(
    team_abbr: str,
    trade: TradeRequest,
    iterations: int = Query(default=1000, ge=100, le=10000),
) -> dict:
    if not trade.remove_player_ids and not trade.add_player_ids:
        raise HTTPException(status_code=400, detail="Add at least one player to trade for or away.")

    try:
        baseline = roster_service.get_baseline(team_abbr.upper())
        if not baseline:
            await roster_service.get_roster(team_abbr)
            baseline = roster_service.get_baseline(team_abbr.upper())

        updated = await roster_service.apply_trade(team_abbr, trade)
        comparison = await simulator.compare_scenarios(
            baseline or updated,
            updated,
            iterations=iterations,
        )
        return {
            "roster": updated,
            "comparison": comparison,
            "trade": trade.model_dump(),
        }
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{team_abbr}/reset", response_model=RosterChart)
async def reset_roster(team_abbr: str) -> RosterChart:
    try:
        return roster_service.reset_to_baseline(team_abbr)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{team_abbr}/compare-baseline", response_model=ScenarioComparison)
async def compare_to_baseline(
    team_abbr: str,
    iterations: int = Query(default=1000, ge=100, le=10000),
) -> ScenarioComparison:
    baseline = roster_service.get_baseline(team_abbr.upper())
    if not baseline:
        raise HTTPException(status_code=400, detail="Load the roster first to establish a baseline.")
    current = await roster_service.get_roster(team_abbr)
    return await simulator.compare_scenarios(deepcopy(baseline), current, iterations=iterations)


@router.get("/{team_abbr}/rating")
async def get_team_rating(team_abbr: str) -> dict:
    chart = await roster_service.get_roster(team_abbr)
    return {
        "team": chart.team_name,
        "abbreviation": chart.team_abbreviation,
        "team_rating": round(chart.team_rating, 2),
        "total_minutes": chart.total_allocated_minutes,
        "player_count": len(chart.players),
    }
