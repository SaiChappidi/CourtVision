"""In-memory roster state management with minute allocation."""

import logging
from copy import deepcopy

from app.gateway.nba_client import TEAM_ID_MAP, TEAM_NAME_MAP, nba_client
from app.models.roster import MinuteAllocation, PlayerProfile, Position, RosterChart, RosterUpdatePayload

logger = logging.getLogger(__name__)

POSITION_MAP = {
    "G": Position.PG, "G-F": Position.SG, "F-G": Position.SF,
    "F": Position.PF, "F-C": Position.C, "C-F": Position.C, "C": Position.C,
    "PG": Position.PG, "SG": Position.SG, "SF": Position.SF, "PF": Position.PF,
}


class RosterService:
    def __init__(self):
        self._rosters: dict[str, RosterChart] = {}

    async def load_roster(self, team_abbr: str, season: str | None = None) -> RosterChart:
        from app.config import settings

        season = season or settings.default_season
        abbr = team_abbr.upper()
        roster_data = await nba_client.get_team_roster(abbr, season)
        players_raw = nba_client.parse_roster_response(roster_data, abbr)

        stats_map: dict[int, dict] = {}
        try:
            stats_data = await nba_client.get_player_stats(season)
            stats_map = nba_client.parse_player_stats(stats_data)
        except ConnectionError:
            logger.warning("Player stats unavailable for %s — using roster defaults", season)

        players: list[PlayerProfile] = []
        for p in players_raw:
            pid = p["player_id"]
            stats = stats_map.get(pid, {})
            pos_str = p.get("position", "SF") or "SF"
            pos = POSITION_MAP.get(pos_str, Position.SF)

            profile = PlayerProfile(
                player_id=pid,
                name=p["name"],
                team=abbr,
                position=pos,
                age=p.get("age", 25),
                games_played=stats.get("games_played", 0),
                minutes_per_game=float(stats.get("minutes_per_game", 0)),
                points_per_game=float(stats.get("points_per_game", 0)),
                rebounds_per_game=float(stats.get("rebounds_per_game", 0)),
                assists_per_game=float(stats.get("assists_per_game", 0)),
                steals_per_game=float(stats.get("steals_per_game", 0)),
                blocks_per_game=float(stats.get("blocks_per_game", 0)),
                field_goal_pct=float(stats.get("field_goal_pct", 0)),
                three_point_pct=float(stats.get("three_point_pct", 0)),
                free_throw_pct=float(stats.get("free_throw_pct", 0)),
                plus_minus=float(stats.get("plus_minus", 0)),
            )
            players.append(profile)

        players.sort(key=lambda x: x.overall_rating, reverse=True)

        default_minutes = self._default_minute_allocation(players)
        chart = RosterChart(
            team_id=TEAM_ID_MAP.get(abbr, 0),
            team_name=TEAM_NAME_MAP.get(abbr, abbr),
            team_abbreviation=abbr,
            season=season,
            players=players,
            minute_allocations=default_minutes,
        )
        self._rosters[abbr] = chart
        return chart

    def _default_minute_allocation(self, players: list[PlayerProfile]) -> list[MinuteAllocation]:
        if not players:
            return []

        top_players = players[:10]
        total_mpg = sum(p.minutes_per_game for p in top_players)

        if total_mpg <= 0:
            per_player = round(240.0 / len(top_players), 1)
            return [
                MinuteAllocation(player_id=p.player_id, player_name=p.name, minutes=min(48, per_player))
                for p in top_players
            ]

        allocations = []
        remaining = 240.0

        for i, player in enumerate(top_players):
            if i == len(top_players) - 1:
                mins = max(0, min(48, remaining))
            else:
                share = player.minutes_per_game / total_mpg
                mins = round(min(48, share * 240), 1)
                remaining -= mins
            allocations.append(MinuteAllocation(
                player_id=player.player_id,
                player_name=player.name,
                minutes=mins,
            ))
        return allocations

    async def get_roster(self, team_abbr: str, season: str | None = None) -> RosterChart:
        abbr = team_abbr.upper()
        if abbr not in self._rosters:
            return await self.load_roster(abbr, season)
        return self._rosters[abbr]

    def update_roster(self, payload: RosterUpdatePayload) -> RosterChart:
        abbr = payload.team_abbreviation.upper()
        if abbr not in self._rosters:
            raise ValueError(f"Roster not loaded for {abbr}. Load it first via GET /roster/{abbr}")

        chart = deepcopy(self._rosters[abbr])

        if payload.remove_players:
            remove_set = set(payload.remove_players)
            chart.players = [p for p in chart.players if p.player_id not in remove_set]
            chart.minute_allocations = [
                m for m in chart.minute_allocations if m.player_id not in remove_set
            ]

        chart.minute_allocations = payload.minute_allocations
        self._rosters[abbr] = chart
        return chart

    def get_cached_teams(self) -> list[str]:
        return list(self._rosters.keys())


roster_service = RosterService()
