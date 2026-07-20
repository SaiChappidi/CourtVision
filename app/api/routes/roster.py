"""Roster management API routes."""

from fastapi import APIRouter, HTTPException

from app.models.roster import RosterChart, RosterUpdatePayload
from app.services.roster_service import roster_service

router = APIRouter(prefix="/roster", tags=["Roster Management"])


@router.get("/{team_abbr}", response_model=RosterChart)
async def get_team_roster(team_abbr: str, season: str = "2025-26") -> RosterChart:
    return await roster_service.get_roster(team_abbr, season)


@router.put("/{team_abbr}", response_model=RosterChart)
async def update_roster(team_abbr: str, payload: RosterUpdatePayload) -> RosterChart:
    payload.team_abbreviation = team_abbr.upper()
    try:
        return roster_service.update_roster(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
