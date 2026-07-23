"""Rating and simulation calibration tests."""

from app.models.roster import MinuteAllocation, PlayerProfile, Position, RosterChart
from app.models.simulation import SimulationRequest
from app.simulator.monte_carlo import MonteCarloSimulator, LEAGUE_AVG_RATING


def _shai() -> PlayerProfile:
    return PlayerProfile(
        player_id=1,
        name="Shai Gilgeous-Alexander",
        team="OKC",
        position=Position.PG,
        points_per_game=32.7,
        rebounds_per_game=5.0,
        assists_per_game=6.4,
        steals_per_game=1.7,
        blocks_per_game=1.0,
        field_goal_pct=0.519,
        three_point_pct=0.375,
        free_throw_pct=0.898,
        plus_minus=9.5,
        minutes_per_game=34.0,
    )


def _rotation_player() -> PlayerProfile:
    return PlayerProfile(
        player_id=2,
        name="Role Player",
        team="OKC",
        position=Position.SF,
        points_per_game=8.0,
        rebounds_per_game=3.5,
        assists_per_game=1.5,
        steals_per_game=0.6,
        blocks_per_game=0.3,
        field_goal_pct=0.44,
        three_point_pct=0.34,
        free_throw_pct=0.75,
        plus_minus=1.0,
        minutes_per_game=18.0,
    )


def _bad_team_player() -> PlayerProfile:
    return PlayerProfile(
        player_id=3,
        name="Tank Commander",
        team="WAS",
        position=Position.PG,
        points_per_game=14.0,
        rebounds_per_game=2.5,
        assists_per_game=4.0,
        steals_per_game=0.8,
        blocks_per_game=0.2,
        field_goal_pct=0.41,
        three_point_pct=0.32,
        free_throw_pct=0.78,
        plus_minus=-8.0,
        minutes_per_game=30.0,
    )


def _build_chart(abbr: str, name: str, players: list[PlayerProfile]) -> RosterChart:
    total_mpg = sum(p.minutes_per_game for p in players) or float(len(players))
    allocations = []
    remaining = 240.0
    for i, p in enumerate(players):
        if i == len(players) - 1:
            mins = max(0, min(48, remaining))
        else:
            mins = round(min(48, (p.minutes_per_game / total_mpg) * 240), 1)
            remaining -= mins
        allocations.append(MinuteAllocation(player_id=p.player_id, player_name=p.name, minutes=mins))
    return RosterChart(
        team_id=1,
        team_name=name,
        team_abbreviation=abbr,
        season="2024-25",
        players=players,
        minute_allocations=allocations,
    )


def test_superstar_rating_is_elite():
    assert _shai().overall_rating >= 88


def test_bad_team_player_rating_is_low():
    assert _bad_team_player().overall_rating < 65


def test_elite_roster_projects_high_wins():
    sim = MonteCarloSimulator(iterations=800)
    elite = [_shai()]
    for i in range(2):
        elite.append(_shai().model_copy(update={"player_id": 10 + i, "name": f"Star {i}"}))
    elite += [_rotation_player().model_copy(update={"player_id": 20 + i}) for i in range(5)]
    chart = _build_chart("OKC", "Thunder", elite)
    import asyncio
    result = asyncio.run(sim.simulate(chart, SimulationRequest(team_abbreviation="OKC", iterations=800)))
    assert result.season_projection.mean_wins >= 55
    assert result.season_projection.win_pct >= 0.65


def test_weak_roster_projects_low_wins():
    sim = MonteCarloSimulator(iterations=800)
    weak = [_bad_team_player() for _ in range(8)]
    chart = _build_chart("WAS", "Wizards", weak)
    import asyncio
    result = asyncio.run(sim.simulate(chart, SimulationRequest(team_abbreviation="WAS", iterations=800)))
    assert result.season_projection.mean_wins <= 35


def test_win_probability_calibration():
    sim = MonteCarloSimulator()
    avg = sim._win_probability(LEAGUE_AVG_RATING)
    elite = sim._win_probability(76.0)
    bad = sim._win_probability(55.0)
    assert 0.45 <= avg <= 0.55
    assert elite >= 0.75
    assert bad <= 0.35


def test_playoff_bracket_orders_correctly():
    sim = MonteCarloSimulator()
    bracket = sim.project_playoff_bracket(76.0, 0.95)
    assert bracket.make_playoffs >= bracket.win_round_1 >= bracket.win_round_2
    assert bracket.win_round_2 >= bracket.reach_finals >= bracket.win_championship
