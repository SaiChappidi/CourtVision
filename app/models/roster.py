from enum import Enum

from pydantic import BaseModel, Field, field_validator


class Position(str, Enum):
    PG = "PG"
    SG = "SG"
    SF = "SF"
    PF = "PF"
    C = "C"


class PlayerProfile(BaseModel):
    player_id: int
    name: str
    team: str
    position: Position = Position.SF
    age: int = 25
    games_played: int = 0
    minutes_per_game: float = 0.0
    points_per_game: float = 0.0
    rebounds_per_game: float = 0.0
    assists_per_game: float = 0.0
    steals_per_game: float = 0.0
    blocks_per_game: float = 0.0
    field_goal_pct: float = 0.0
    three_point_pct: float = 0.0
    free_throw_pct: float = 0.0
    plus_minus: float = 0.0
    win_shares: float = 0.0
    offensive_rating: float = 110.0
    defensive_rating: float = 110.0

    @property
    def net_rating(self) -> float:
        return self.offensive_rating - self.defensive_rating

    @property
    def overall_rating(self) -> float:
        """Composite player rating on a ~30-99 scale.

        Calibrated so that superstars land in the low-to-mid 90s, quality
        starters in the 75-85 range, rotation players in the low 60s, and
        deep-bench players in the low 50s.
        """
        # Box-score production index (per game), weighting playmaking and
        # defensive events like a simplified game score.
        box_production = (
            self.points_per_game * 1.00
            + self.rebounds_per_game * 1.20
            + self.assists_per_game * 1.50
            + self.steals_per_game * 3.00
            + self.blocks_per_game * 3.00
        )

        # On/off impact: per-game plus/minus captures team context and the
        # defensive value box scores miss, and cleanly separates contributors
        # on good teams from volume players on bad ones. Bounded to avoid
        # letting a single blowout-heavy season dominate.
        impact = max(-9.0, min(11.0, self.plus_minus)) * 1.6

        # Shooting efficiency, bounded so it nudges rather than dominates.
        efficiency = (
            (self.field_goal_pct - 0.46) * 30
            + (self.three_point_pct - 0.35) * 8
            + (self.free_throw_pct - 0.75) * 4
        )
        efficiency = max(-6.0, min(8.0, efficiency))

        # Players with essentially no measured production (missing data or
        # end-of-bench) shouldn't be penalised by the shooting term.
        if box_production < 3.0:
            efficiency = 0.0

        rating = 40.0 + 0.78 * box_production + impact + efficiency
        return max(25.0, min(99.0, rating))


class MinuteAllocation(BaseModel):
    player_id: int
    player_name: str
    minutes: float = Field(ge=0, le=48, description="Minutes per game allocation")

    @field_validator("minutes")
    @classmethod
    def round_minutes(cls, v: float) -> float:
        return round(v, 1)


class RosterChart(BaseModel):
    team_id: int
    team_name: str
    team_abbreviation: str
    season: str = "2024-25"
    players: list[PlayerProfile] = Field(default_factory=list)
    minute_allocations: list[MinuteAllocation] = Field(default_factory=list)

    @property
    def total_allocated_minutes(self) -> float:
        return sum(m.minutes for m in self.minute_allocations)

    @property
    def team_rating(self) -> float:
        if not self.minute_allocations or not self.players:
            return 50.0
        player_map = {p.player_id: p for p in self.players}
        weighted = 0.0
        total_mins = 0.0
        for alloc in self.minute_allocations:
            player = player_map.get(alloc.player_id)
            if player:
                weighted += player.overall_rating * alloc.minutes
                total_mins += alloc.minutes
        return weighted / total_mins if total_mins > 0 else 50.0


class RosterUpdatePayload(BaseModel):
    team_abbreviation: str
    minute_allocations: list[MinuteAllocation]
    add_players: list[int] = Field(default_factory=list, description="Player IDs to add")
    remove_players: list[int] = Field(default_factory=list, description="Player IDs to remove")
    notes: str = ""

    @field_validator("minute_allocations")
    @classmethod
    def validate_total_minutes(cls, allocations: list[MinuteAllocation]) -> list[MinuteAllocation]:
        total = sum(a.minutes for a in allocations)
        if total > 240:
            raise ValueError(f"Total minutes ({total}) exceeds 240 per game")
        return allocations
