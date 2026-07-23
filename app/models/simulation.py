from pydantic import BaseModel, Field


class TeamStanding(BaseModel):
    team_abbreviation: str
    team_name: str
    wins: float
    losses: float
    win_pct: float
    conference_rank: int = 0
    playoff_seed: int | None = None


class PlayoffBracketProjection(BaseModel):
    """Cumulative playoff advancement probabilities (best-of-7 model)."""
    make_playoffs: float = Field(default=0.0, ge=0, le=1)
    win_round_1: float = Field(default=0.0, ge=0, le=1)
    win_round_2: float = Field(default=0.0, ge=0, le=1)
    reach_finals: float = Field(default=0.0, ge=0, le=1)
    win_championship: float = Field(default=0.0, ge=0, le=1)


class PlayoffProjection(BaseModel):
    team_abbreviation: str
    playoff_probability: float = Field(ge=0, le=1)
    projected_seed: int | None = None
    play_in_probability: float = Field(default=0.0, ge=0, le=1)
    bracket: PlayoffBracketProjection = Field(default_factory=PlayoffBracketProjection)


class SeasonProjection(BaseModel):
    mean_wins: float
    median_wins: float
    std_wins: float
    win_pct: float
    win_distribution: dict[int, float] = Field(default_factory=dict)
    percentile_10: float = 0.0
    percentile_90: float = 0.0


class SimulationRequest(BaseModel):
    team_abbreviation: str
    iterations: int = Field(default=1000, ge=100, le=10000)
    season_games: int = Field(default=82, ge=1, le=82)
    opponent_strength: float = Field(
        default=0.0, ge=0, le=100,
        description="League baseline rating for schedule strength. 0 = use default (.500 anchor).",
    )


class SimulationResult(BaseModel):
    team_abbreviation: str
    team_name: str
    team_rating: float
    season: str = ""
    iterations: int
    season_projection: SeasonProjection
    playoff_projection: PlayoffProjection
    roster_summary: list[dict] = Field(default_factory=list)


class TeamCompareRequest(BaseModel):
    team_a: str
    team_b: str
    iterations: int = Field(default=1000, ge=100, le=10000)
    season: str | None = None


class TeamCompareResult(BaseModel):
    team_a: SimulationResult
    team_b: SimulationResult
    rating_winner: str
    wins_winner: str
    win_delta: float


class ScenarioComparison(BaseModel):
    baseline: SimulationResult
    current: SimulationResult
    wins_delta: float
    rating_delta: float
    playoff_delta: float
