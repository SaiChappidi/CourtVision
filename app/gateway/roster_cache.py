"""Disk cache for NBA roster and stats data when the live API is unavailable."""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"


def _ensure_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _roster_path(team_abbr: str, season: str) -> Path:
    return CACHE_DIR / f"roster_{team_abbr.upper()}_{season.replace('-', '_')}.json"


def _stats_path(season: str) -> Path:
    return CACHE_DIR / f"player_stats_{season.replace('-', '_')}.json"


def save_roster(team_abbr: str, season: str, data: dict[str, Any]) -> None:
    _ensure_dir()
    path = _roster_path(team_abbr, season)
    path.write_text(json.dumps(data), encoding="utf-8")
    logger.debug("Cached roster %s %s", team_abbr, season)


def load_roster(team_abbr: str, season: str) -> dict[str, Any] | None:
    path = _roster_path(team_abbr, season)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read roster cache: %s", exc)
        return None


def save_player_stats(season: str, data: dict[str, Any]) -> None:
    _ensure_dir()
    path = _stats_path(season)
    path.write_text(json.dumps(data), encoding="utf-8")
    logger.debug("Cached player stats for %s", season)


def load_player_stats(season: str) -> dict[str, Any] | None:
    path = _stats_path(season)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read stats cache: %s", exc)
        return None
