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
        """Composite player rating on a 0-100 scale."""
        base = (
            self.points_per_game * 0.35
            + self.rebounds_per_game * 0.15
            + self.assists_per_game * 0.20
            + self.steals_per_game * 2.0
            + self.blocks_per_game * 2.0
            + self.plus_minus * 0.5
            + self.win_shares * 3.0
        )
        efficiency_bonus = (self.field_goal_pct - 0.42) * 20 + (self.three_point_pct - 0.35) * 10
        return max(0.0, min(100.0, base + efficiency_bonus + 30))


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
