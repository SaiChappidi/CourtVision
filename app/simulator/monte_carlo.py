"""Asynchronous Monte Carlo season simulator."""

import asyncio
import logging
from collections import Counter
from math import comb

import numpy as np

from app.config import settings
from app.models.roster import RosterChart
from app.models.simulation import (
    PlayoffBracketProjection,
    PlayoffProjection,
    ScenarioComparison,
    SeasonProjection,
    SimulationRequest,
    SimulationResult,
    TeamCompareRequest,
    TeamCompareResult,
)

logger = logging.getLogger(__name__)

PLAYOFF_WIN_THRESHOLD = 42.0
PLAY_IN_WIN_THRESHOLD = 38.0

LEAGUE_AVG_RATING = 63.0
RATING_SCALE = 4.2
MIN_WIN_PROB = 0.16
MAX_WIN_PROB = 0.85

# Typical opponent strength by playoff round (rating scale).
PLAYOFF_ROUND_OPPONENTS = [65.0, 68.0, 70.0, 72.0]


class MonteCarloSimulator:
    """
    Runs N asynchronous seasonal Monte Carlo iterations to project
    team standings, win-loss percentages, and playoff viability.
    """

    def __init__(self, iterations: int | None = None):
        self.iterations = iterations or settings.monte_carlo_iterations

    def _win_probability(self, team_rating: float, baseline: float = LEAGUE_AVG_RATING) -> float:
        rating_diff = team_rating - baseline
        prob = 1.0 / (1.0 + np.exp(-rating_diff / RATING_SCALE))
        return float(np.clip(prob, MIN_WIN_PROB, MAX_WIN_PROB))

    @staticmethod
    def _best_of_seven_prob(p_game: float) -> float:
        p_game = float(np.clip(p_game, 0.05, 0.95))
        return sum(comb(7, k) * (p_game ** k) * ((1 - p_game) ** (7 - k)) for k in range(4, 8))

    def project_playoff_bracket(
        self,
        team_rating: float,
        playoff_probability: float,
    ) -> PlayoffBracketProjection:
        if playoff_probability <= 0.01:
            return PlayoffBracketProjection()

        cumulative = playoff_probability
        round_probs = [cumulative]

        for opp_rating in PLAYOFF_ROUND_OPPONENTS:
            p_game = self._win_probability(team_rating, opp_rating)
            p_series = self._best_of_seven_prob(p_game)
            cumulative *= p_series
            round_probs.append(cumulative)

        return PlayoffBracketProjection(
            make_playoffs=round_probs[0],
            win_round_1=round_probs[1],
            win_round_2=round_probs[2],
            reach_finals=round_probs[3],
            win_championship=round_probs[4],
        )

    def _simulate_season(
        self,
        team_rating: float,
        opponent_strength: float,
        season_games: int,
        rng: np.random.Generator,
    ) -> int:
        baseline = opponent_strength if opponent_strength else LEAGUE_AVG_RATING
        win_prob = self._win_probability(team_rating, baseline)
        noise = rng.normal(0, 0.025)
        adjusted_prob = float(np.clip(win_prob + noise, MIN_WIN_PROB, MAX_WIN_PROB))
        return int(rng.binomial(season_games, adjusted_prob))

    async def _run_single_iteration(
        self,
        team_rating: float,
        opponent_strength: float,
        season_games: int,
        seed: int,
    ) -> int:
        rng = np.random.default_rng(seed)
        return self._simulate_season(team_rating, opponent_strength, season_games, rng)

    async def simulate(self, roster: RosterChart, request: SimulationRequest) -> SimulationResult:
        team_rating = roster.team_rating
        iterations = request.iterations or self.iterations
        season_games = request.season_games
        opponent_strength = request.opponent_strength

        tasks = [
            self._run_single_iteration(team_rating, opponent_strength, season_games, seed=i)
            for i in range(iterations)
        ]
        win_counts = await asyncio.gather(*tasks)

        wins_array = np.array(win_counts, dtype=float)
        win_distribution = Counter(win_counts)
        total = len(win_counts)
        distribution_pct = {k: v / total for k, v in sorted(win_distribution.items())}

        season_projection = SeasonProjection(
            mean_wins=float(np.mean(wins_array)),
            median_wins=float(np.median(wins_array)),
            std_wins=float(np.std(wins_array)),
            win_pct=float(np.mean(wins_array) / season_games),
            win_distribution={int(k): round(v, 4) for k, v in distribution_pct.items()},
            percentile_10=float(np.percentile(wins_array, 10)),
            percentile_90=float(np.percentile(wins_array, 90)),
        )

        playoff_count = sum(1 for w in win_counts if w >= PLAYOFF_WIN_THRESHOLD)
        playin_count = sum(
            1 for w in win_counts
            if PLAY_IN_WIN_THRESHOLD <= w < PLAYOFF_WIN_THRESHOLD
        )
        playoff_prob = playoff_count / total

        projected_seed = None
        if season_projection.mean_wins >= PLAYOFF_WIN_THRESHOLD:
            projected_seed = max(1, min(8, int(9 - (season_projection.mean_wins - 42) / 3)))

        bracket = self.project_playoff_bracket(team_rating, playoff_prob)

        playoff_projection = PlayoffProjection(
            team_abbreviation=roster.team_abbreviation,
            playoff_probability=playoff_prob,
            projected_seed=projected_seed,
            play_in_probability=playin_count / total,
            bracket=bracket,
        )

        roster_summary = []
        player_map = {p.player_id: p for p in roster.players}
        for alloc in roster.minute_allocations:
            player = player_map.get(alloc.player_id)
            if player:
                roster_summary.append({
                    "name": player.name,
                    "position": player.position.value,
                    "minutes": alloc.minutes,
                    "rating": round(player.overall_rating, 1),
                    "ppg": player.points_per_game,
                })

        return SimulationResult(
            team_abbreviation=roster.team_abbreviation,
            team_name=roster.team_name,
            team_rating=round(team_rating, 2),
            season=roster.season,
            iterations=iterations,
            season_projection=season_projection,
            playoff_projection=playoff_projection,
            roster_summary=roster_summary,
        )

    async def compare_scenarios(
        self,
        baseline: RosterChart,
        current: RosterChart,
        iterations: int = 1000,
    ) -> ScenarioComparison:
        base_req = SimulationRequest(team_abbreviation=baseline.team_abbreviation, iterations=iterations)
        cur_req = SimulationRequest(team_abbreviation=current.team_abbreviation, iterations=iterations)
        base_sim, cur_sim = await asyncio.gather(
            self.simulate(baseline, base_req),
            self.simulate(current, cur_req),
        )
        return ScenarioComparison(
            baseline=base_sim,
            current=cur_sim,
            wins_delta=cur_sim.season_projection.mean_wins - base_sim.season_projection.mean_wins,
            rating_delta=cur_sim.team_rating - base_sim.team_rating,
            playoff_delta=(
                cur_sim.playoff_projection.playoff_probability
                - base_sim.playoff_projection.playoff_probability
            ),
        )

    async def compare_teams(
        self,
        roster_a: RosterChart,
        roster_b: RosterChart,
        request: TeamCompareRequest,
    ) -> TeamCompareResult:
        req_a = SimulationRequest(team_abbreviation=roster_a.team_abbreviation, iterations=request.iterations)
        req_b = SimulationRequest(team_abbreviation=roster_b.team_abbreviation, iterations=request.iterations)
        sim_a, sim_b = await asyncio.gather(
            self.simulate(roster_a, req_a),
            self.simulate(roster_b, req_b),
        )
        rating_winner = sim_a.team_abbreviation if sim_a.team_rating >= sim_b.team_rating else sim_b.team_abbreviation
        wins_winner = (
            sim_a.team_abbreviation
            if sim_a.season_projection.mean_wins >= sim_b.season_projection.mean_wins
            else sim_b.team_abbreviation
        )
        return TeamCompareResult(
            team_a=sim_a,
            team_b=sim_b,
            rating_winner=rating_winner,
            wins_winner=wins_winner,
            win_delta=sim_a.season_projection.mean_wins - sim_b.season_projection.mean_wins,
        )


simulator = MonteCarloSimulator()
