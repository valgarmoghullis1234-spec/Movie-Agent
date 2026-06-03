"""Application settings, loaded from environment / .env file.

Everything is optional so the app boots even with no keys (echo + no-trace mode),
which keeps Phase 0 friction-free while you wire up accounts.
"""
from functools import lru_cache
from typing import Any, Tuple, Type

from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


class _NonEmptyEnvSource(EnvSettingsSource):
    """Env source that ignores blank values.

    Without this, an exported but empty var (e.g. `ANTHROPIC_API_KEY=""` in the shell)
    would shadow the real value in `.env`, silently dropping the app into echo mode. By
    dropping empty env values, blank vars fall through to `.env`/defaults instead.
    """

    def __call__(self) -> dict[str, Any]:
        return {k: v for k, v in super().__call__().items() if not (isinstance(v, str) and v == "")}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        # Replace the default env source with one that ignores empty values, so a blank
        # exported var never overrides .env. Priority order otherwise unchanged.
        return (
            init_settings,
            _NonEmptyEnvSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )

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
