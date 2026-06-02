"""Application settings, loaded from environment / .env file.

Everything is optional so the app boots even with no keys (echo + no-trace mode),
which keeps Phase 0 friction-free while you wire up accounts.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5"

    # Langfuse
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # TMDB (Phase 1+)
    tmdb_api_key: str = ""

    # OMDb (fallback data source + IMDb/RT/Metacritic ratings)
    omdb_api_key: str = ""

    # Server
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def omdb_enabled(self) -> bool:
        return bool(self.omdb_api_key)

    @property
    def tracing_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
