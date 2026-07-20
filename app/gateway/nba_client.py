"""NBA API client with caching and header rotation."""

import asyncio
import logging
from typing import Any

import httpx

from app.config import settings
from app.gateway.cache import cache
from app.gateway.headers import header_rotator

logger = logging.getLogger(__name__)

NBA_STATS_BASE = "https://stats.nba.com/stats"
NBA_DATA_BASE = "https://data.nba.net/prod/v1"

TEAM_ID_MAP: dict[str, int] = {
    "ATL": 1610612737, "BOS": 1610612738, "BKN": 1610612751, "CHA": 1610612766,
    "CHI": 1610612741, "CLE": 1610612739, "DAL": 1610612742, "DEN": 1610612743,
    "DET": 1610612765, "GSW": 1610612744, "HOU": 1610612745, "IND": 1610612754,
    "LAC": 1610612746, "LAL": 1610612747, "MEM": 1610612763, "MIA": 1610612748,
    "MIL": 1610612749, "MIN": 1610612750, "NOP": 1610612740, "NYK": 1610612752,
    "OKC": 1610612760, "ORL": 1610612753, "PHI": 1610612755, "PHX": 1610612756,
    "POR": 1610612757, "SAC": 1610612758, "SAS": 1610612759, "TOR": 1610612761,
    "UTA": 1610612762, "WAS": 1610612764,
}

TEAM_NAME_MAP: dict[str, str] = {
    "ATL": "Atlanta Hawks", "BOS": "Boston Celtics", "BKN": "Brooklyn Nets",
    "CHA": "Charlotte Hornets", "CHI": "Chicago Bulls", "CLE": "Cleveland Cavaliers",
    "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets", "DET": "Detroit Pistons",
    "GSW": "Golden State Warriors", "HOU": "Houston Rockets", "IND": "Indiana Pacers",
    "LAC": "LA Clippers", "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies",
    "MIA": "Miami Heat", "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves",
    "NOP": "New Orleans Pelicans", "NYK": "New York Knicks", "OKC": "Oklahoma City Thunder",
    "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers", "PHX": "Phoenix Suns",
    "POR": "Portland Trail Blazers", "SAC": "Sacramento Kings", "SAS": "San Antonio Spurs",
    "TOR": "Toronto Raptors", "UTA": "Utah Jazz", "WAS": "Washington Wizards",
}


from app.config import settings

DEFAULT_SEASON = settings.default_season


class NBAClient:
    """Async client for official NBA stats endpoints."""

    def __init__(self):
        self.timeout = settings.nba_request_timeout
        self.max_retries = settings.nba_max_retries

    async def _request(self, url: str, params: dict | None = None) -> dict[str, Any]:
        cache_key_parts = [url, str(sorted((params or {}).items()))]
        cached = await cache.get("nba", *cache_key_parts)
        if cached is not None:
            return cached

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            headers = header_rotator.next_headers()
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(url, params=params, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                    await cache.set("nba", data, *cache_key_parts)
                    return data
            except Exception as exc:
                last_error = exc
                logger.warning("NBA API attempt %d failed: %s", attempt + 1, exc)
                await asyncio.sleep(0.5 * (attempt + 1))

        raise ConnectionError(f"NBA API request failed after {self.max_retries} retries: {last_error}")

    async def get_team_roster(self, team_abbr: str, season: str | None = None) -> dict[str, Any]:
        season = season or DEFAULT_SEASON
        team_id = TEAM_ID_MAP.get(team_abbr.upper())
        if not team_id:
            raise ValueError(f"Unknown team abbreviation: {team_abbr}")

        url = f"{NBA_STATS_BASE}/commonteamroster"
        params = {"TeamID": team_id, "Season": season}
        return await self._request(url, params)

    async def get_league_standings(self, season: str | None = None) -> dict[str, Any]:
        season = season or DEFAULT_SEASON
        url = f"{NBA_STATS_BASE}/leaguestandingsv3"
        params = {"LeagueID": "00", "Season": season, "SeasonType": "Regular Season"}
        return await self._request(url, params)

    async def get_player_stats(self, season: str | None = None) -> dict[str, Any]:
        season = season or DEFAULT_SEASON
        url = f"{NBA_STATS_BASE}/leaguedashplayerstats"
        params = {
            "MeasureType": "Base",
            "PerMode": "PerGame",
            "PlusMinus": "Y",
            "PaceAdjust": "N",
            "Rank": "N",
            "LeagueID": "00",
            "Season": season,
            "SeasonType": "Regular Season",
            "PORound": "0",
        }
        try:
            return await self._request(url, params)
        except ConnectionError:
            return await self._player_stats_via_nba_api(season)

    async def _player_stats_via_nba_api(self, season: str) -> dict[str, Any]:
        """Fallback using nba_api library which handles headers internally."""
        import asyncio
        from nba_api.stats.endpoints import leaguedashplayerstats

        def _fetch():
            endpoint = leaguedashplayerstats.LeagueDashPlayerStats(
                season=season,
                per_mode_detailed="PerGame",
                measure_type_detailed_defense="Base",
            )
            return endpoint.get_dict()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _fetch)

    async def get_team_stats(self, season: str | None = None) -> dict[str, Any]:
        season = season or DEFAULT_SEASON
        url = f"{NBA_STATS_BASE}/leaguedashteamstats"
        params = {
            "MeasureType": "Base",
            "PerMode": "PerGame",
            "PlusMinus": "Y",
            "Rank": "N",
            "LeagueID": "00",
            "Season": season,
            "SeasonType": "Regular Season",
        }
        return await self._request(url, params)

    async def search_player(self, name: str) -> list[dict[str, Any]]:
        from nba_api.stats.static import players

        matches = players.find_players_by_full_name(name)
        return [{"id": p["id"], "full_name": p["full_name"], "is_active": p["is_active"]} for p in matches]

    @staticmethod
    def parse_roster_response(data: dict[str, Any], team_abbr: str) -> list[dict[str, Any]]:
        result_sets = data.get("resultSets", [])
        if not result_sets:
            return []

        headers = result_sets[0]["headers"]
        rows = result_sets[0]["rowSet"]
        players_list = []
        for row in rows:
            player = dict(zip(headers, row))
            players_list.append({
                "player_id": player.get("PLAYER_ID"),
                "name": player.get("PLAYER"),
                "position": player.get("POSITION", "SF"),
                "height": player.get("HEIGHT"),
                "weight": player.get("WEIGHT"),
                "age": player.get("AGE", 25),
                "team": team_abbr.upper(),
            })
        return players_list

    @staticmethod
    def parse_player_stats(data: dict[str, Any]) -> dict[int, dict[str, Any]]:
        result_sets = data.get("resultSets", [])
        if not result_sets:
            return {}

        headers = result_sets[0]["headers"]
        rows = result_sets[0]["rowSet"]
        stats_map: dict[int, dict[str, Any]] = {}
        for row in rows:
            player = dict(zip(headers, row))
            pid = player.get("PLAYER_ID")
            if pid:
                stats_map[pid] = {
                    "games_played": player.get("GP", 0),
                    "minutes_per_game": player.get("MIN", 0.0),
                    "points_per_game": player.get("PTS", 0.0),
                    "rebounds_per_game": player.get("REB", 0.0),
                    "assists_per_game": player.get("AST", 0.0),
                    "steals_per_game": player.get("STL", 0.0),
                    "blocks_per_game": player.get("BLK", 0.0),
                    "field_goal_pct": player.get("FG_PCT", 0.0),
                    "three_point_pct": player.get("FG3_PCT", 0.0),
                    "free_throw_pct": player.get("FT_PCT", 0.0),
                    "plus_minus": player.get("PLUS_MINUS", 0.0),
                    "team": player.get("TEAM_ABBREVIATION", ""),
                }
        return stats_map


nba_client = NBAClient()
