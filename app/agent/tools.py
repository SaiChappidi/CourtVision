"""LangChain tool definitions for the GM agent."""

import json
from typing import Any

from langchain_core.tools import tool

from app.models.roster import MinuteAllocation, RosterUpdatePayload
from app.models.simulation import SimulationRequest
from app.services.roster_service import roster_service
from app.simulator.monte_carlo import simulator


@tool
async def get_team_roster(team_abbreviation: str) -> str:
    """Fetch the current roster and minute allocations for an NBA team.
    team_abbreviation: 3-letter team code (e.g. LAL, BOS, GSW)."""
    chart = await roster_service.get_roster(team_abbreviation)
    return json.dumps({
        "team": chart.team_name,
        "abbreviation": chart.team_abbreviation,
        "team_rating": round(chart.team_rating, 2),
        "total_minutes": chart.total_allocated_minutes,
        "players": [
            {
                "id": p.player_id,
                "name": p.name,
                "position": p.position.value,
                "rating": round(p.overall_rating, 1),
                "ppg": p.points_per_game,
                "mpg": p.minutes_per_game,
            }
            for p in chart.players
        ],
        "minute_allocations": [
            {"player_id": m.player_id, "name": m.player_name, "minutes": m.minutes}
            for m in chart.minute_allocations
        ],
    })


@tool
async def update_minute_allocations(
    team_abbreviation: str,
    allocations_json: str,
) -> str:
    """Update minute allocations for a team roster.
    team_abbreviation: 3-letter team code.
    allocations_json: JSON array of {player_id, player_name, minutes} objects. Total must not exceed 240."""
    allocations_data = json.loads(allocations_json)
    allocations = [MinuteAllocation(**a) for a in allocations_data]
    payload = RosterUpdatePayload(
        team_abbreviation=team_abbreviation,
        minute_allocations=allocations,
    )
    chart = roster_service.update_roster(payload)
    return json.dumps({
        "status": "updated",
        "team": chart.team_name,
        "team_rating": round(chart.team_rating, 2),
        "total_minutes": chart.total_allocated_minutes,
        "allocations": [
            {"name": m.player_name, "minutes": m.minutes}
            for m in chart.minute_allocations
        ],
    })


@tool
async def run_season_simulation(
    team_abbreviation: str,
    iterations: int = 1000,
) -> str:
    """Run Monte Carlo season simulation for a team.
    team_abbreviation: 3-letter team code.
    iterations: number of simulations (default 1000)."""
    chart = await roster_service.get_roster(team_abbreviation)
    request = SimulationRequest(team_abbreviation=team_abbreviation, iterations=iterations)
    result = await simulator.simulate(chart, request)
    return json.dumps({
        "team": result.team_name,
        "team_rating": result.team_rating,
        "iterations": result.iterations,
        "projected_wins": round(result.season_projection.mean_wins, 1),
        "projected_losses": round(82 - result.season_projection.mean_wins, 1),
        "win_pct": round(result.season_projection.win_pct, 3),
        "playoff_probability": round(result.playoff_projection.playoff_probability, 3),
        "projected_seed": result.playoff_projection.projected_seed,
        "win_range": f"{result.season_projection.percentile_10:.0f}-{result.season_projection.percentile_90:.0f}",
    })


@tool
async def search_player(player_name: str) -> str:
    """Search for an NBA player by name.
    player_name: full or partial player name."""
    from app.gateway.nba_client import nba_client

    matches = await nba_client.search_player(player_name)
    return json.dumps(matches[:5])


@tool
async def compare_roster_scenarios(
    team_abbreviation: str,
    scenario_a_json: str,
    scenario_b_json: str,
) -> str:
    """Compare two minute allocation scenarios via simulation.
    team_abbreviation: 3-letter team code.
    scenario_a_json: JSON array of minute allocations for scenario A.
    scenario_b_json: JSON array of minute allocations for scenario B."""
    chart = await roster_service.get_roster(team_abbreviation)
    results = {}

    for label, scenario_json in [("A", scenario_a_json), ("B", scenario_b_json)]:
        allocations = [MinuteAllocation(**a) for a in json.loads(scenario_json)]
        payload = RosterUpdatePayload(team_abbreviation=team_abbreviation, minute_allocations=allocations)
        updated = roster_service.update_roster(payload)
        request = SimulationRequest(team_abbreviation=team_abbreviation, iterations=500)
        sim = await simulator.simulate(updated, request)
        results[label] = {
            "team_rating": sim.team_rating,
            "projected_wins": round(sim.season_projection.mean_wins, 1),
            "playoff_probability": round(sim.playoff_projection.playoff_probability, 3),
        }

    await roster_service.get_roster(team_abbreviation)
    winner = "A" if results["A"]["projected_wins"] > results["B"]["projected_wins"] else "B"
    return json.dumps({"scenario_a": results["A"], "scenario_b": results["B"], "recommended": winner})


ALL_TOOLS = [
    get_team_roster,
    update_minute_allocations,
    run_season_simulation,
    search_player,
    compare_roster_scenarios,
]
