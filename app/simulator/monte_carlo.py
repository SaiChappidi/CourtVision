"""Asynchronous Monte Carlo season simulator."""

import asyncio
import logging
from collections import Counter

import numpy as np

from app.config import settings
from app.models.roster import RosterChart
from app.models.simulation import (
    PlayoffProjection,
    SeasonProjection,
    SimulationRequest,
    SimulationResult,
)

logger = logging.getLogger(__name__)

PLAYOFF_WIN_THRESHOLD = 42.0
PLAY_IN_WIN_THRESHOLD = 38.0


class MonteCarloSimulator:
    """
    Runs N asynchronous seasonal Monte Carlo iterations to project
    team standings, win-loss percentages, and playoff viability.
    """

    def __init__(self, iterations: int | None = None):
        self.iterations = iterations or settings.monte_carlo_iterations

    def _win_probability(self, team_rating: float, opponent_rating: float) -> float:
        rating_diff = team_rating - opponent_rating
        return 1.0 / (1.0 + 10 ** (-rating_diff / 15.0))

    def _simulate_season(
        self,
        team_rating: float,
        opponent_strength: float,
        season_games: int,
        rng: np.random.Generator,
    ) -> int:
        win_prob = self._win_probability(team_rating, opponent_strength)
        noise = rng.normal(0, 0.03)
        adjusted_prob = np.clip(win_prob + noise, 0.15, 0.85)
        wins = int(rng.binomial(season_games, adjusted_prob))
        return wins

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

        projected_seed = None
        if season_projection.mean_wins >= PLAYOFF_WIN_THRESHOLD:
            projected_seed = max(1, min(8, int(9 - (season_projection.mean_wins - 42) / 3)))

        playoff_projection = PlayoffProjection(
            team_abbreviation=roster.team_abbreviation,
            playoff_probability=playoff_count / total,
            projected_seed=projected_seed,
            play_in_probability=playin_count / total,
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
            iterations=iterations,
            season_projection=season_projection,
            playoff_projection=playoff_projection,
            roster_summary=roster_summary,
        )


simulator = MonteCarloSimulator()
