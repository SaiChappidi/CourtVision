from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = False

    redis_url: str = "redis://localhost:6379/0"
    cache_ttl: int = 3600

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash-lite"

    monte_carlo_iterations: int = 1000
    nba_request_timeout: float = 30.0
    nba_max_retries: int = 3
    default_season: str = "2024-25"


settings = Settings()
