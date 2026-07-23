"""In-memory roster state management with minute allocation."""

import logging
from copy import deepcopy

from app.config import settings
from app.gateway.nba_client import TEAM_ID_MAP, TEAM_NAME_MAP, nba_client
from app.gateway import roster_cache
from app.models.roster import MinuteAllocation, PlayerProfile, Position, RosterChart, RosterUpdatePayload, TradeRequest

logger = logging.getLogger(__name__)

POSITION_MAP = {
    "G": Position.PG, "G-F": Position.SG, "F-G": Position.SF,
    "F": Position.PF, "F-C": Position.C, "C-F": Position.C, "C": Position.C,
    "PG": Position.PG, "SG": Position.SG, "SF": Position.SF, "PF": Position.PF,
}


class RosterService:
    def __init__(self):
        self._rosters: dict[str, RosterChart] = {}
        self._baselines: dict[str, RosterChart] = {}
        self._stats_cache: dict[str, dict[int, dict]] = {}

    async def _get_stats_map(self, season: str) -> dict[int, dict]:
        if season in self._stats_cache:
            return self._stats_cache[season]

        stats_data: dict | None = None
        try:
            stats_data = await nba_client.get_player_stats(season)
            roster_cache.save_player_stats(season, stats_data)
        except ConnectionError:
            logger.warning("Live player stats unavailable for %s — trying disk cache", season)
            stats_data = roster_cache.load_player_stats(season)

        if not stats_data:
            self._stats_cache[season] = {}
            return {}

        stats_map = nba_client.parse_player_stats(stats_data)
        self._stats_cache[season] = stats_map
        return stats_map

    async def _player_from_id(
        self,
        player_id: int,
        team_abbr: str,
        season: str,
        stats_map: dict[int, dict],
    ) -> PlayerProfile | None:
        from nba_api.stats.static import players as nba_players

        info = nba_players.find_player_by_id(player_id)
        if not info:
            return None

        stats = stats_map.get(player_id, {})
        return PlayerProfile(
            player_id=player_id,
            name=info["full_name"],
            team=team_abbr.upper(),
            position=Position.SF,
            games_played=int(stats.get("games_played", 0)),
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

    async def load_roster(
        self,
        team_abbr: str,
        season: str | None = None,
        force: bool = False,
    ) -> RosterChart:
        season = season or settings.default_season
        abbr = team_abbr.upper()

        if not force and abbr in self._rosters and self._rosters[abbr].season == season:
            return self._rosters[abbr]

        roster_data: dict | None = None
        try:
            roster_data = await nba_client.get_team_roster(abbr, season)
            roster_cache.save_roster(abbr, season, roster_data)
        except ConnectionError:
            logger.warning("Live roster unavailable for %s — trying disk cache", abbr)
            roster_data = roster_cache.load_roster(abbr, season)

        if not roster_data:
            raise ConnectionError(
                f"Could not load roster for {abbr} ({season}). "
                "The NBA stats API may be down — try again or switch season."
            )

        players_raw = nba_client.parse_roster_response(roster_data, abbr)
        stats_map = await self._get_stats_map(season)

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
        if abbr not in self._baselines:
            self._baselines[abbr] = deepcopy(chart)
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
        season = season or settings.default_season
        abbr = team_abbr.upper()
        if abbr not in self._rosters or self._rosters[abbr].season != season:
            return await self.load_roster(abbr, season)
        return self._rosters[abbr]

    async def reload_roster(self, team_abbr: str, season: str | None = None) -> RosterChart:
        abbr = team_abbr.upper()
        self._baselines.pop(abbr, None)
        return await self.load_roster(abbr, season, force=True)

    def get_baseline(self, team_abbr: str) -> RosterChart | None:
        return self._baselines.get(team_abbr.upper())

    def reset_to_baseline(self, team_abbr: str) -> RosterChart:
        abbr = team_abbr.upper()
        if abbr not in self._baselines:
            raise ValueError(f"No baseline saved for {abbr}. Load the roster first.")
        self._rosters[abbr] = deepcopy(self._baselines[abbr])
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

    async def apply_trade(self, team_abbr: str, trade: TradeRequest) -> RosterChart:
        abbr = team_abbr.upper()
        chart = await self.get_roster(abbr)
        season = chart.season
        stats_map = await self._get_stats_map(season)

        remove_set = set(trade.remove_player_ids)
        chart = deepcopy(chart)
        chart.players = [p for p in chart.players if p.player_id not in remove_set]
        chart.minute_allocations = [
            m for m in chart.minute_allocations if m.player_id not in remove_set
        ]

        for pid in trade.add_player_ids:
            if any(p.player_id == pid for p in chart.players):
                continue
            profile = await self._player_from_id(pid, abbr, season, stats_map)
            if profile:
                chart.players.append(profile)

        chart.players.sort(key=lambda x: x.overall_rating, reverse=True)
        chart.minute_allocations = self._default_minute_allocation(chart.players)
        self._rosters[abbr] = chart
        return chart

    async def get_player_preview(self, player_id: int, season: str | None = None) -> dict | None:
        season = season or settings.default_season
        stats_map = await self._get_stats_map(season)
        profile = await self._player_from_id(player_id, "FA", season, stats_map)
        if not profile:
            return None
        stats = stats_map.get(player_id, {})
        return {
            "player_id": profile.player_id,
            "name": profile.name,
            "team": stats.get("team", ""),
            "rating": round(profile.overall_rating, 1),
            "ppg": profile.points_per_game,
            "rpg": profile.rebounds_per_game,
            "apg": profile.assists_per_game,
            "mpg": profile.minutes_per_game,
        }

    def get_cached_teams(self) -> list[str]:
        return list(self._rosters.keys())


roster_service = RosterService()
