from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings loaded from environment."""

    PROJECT_NAME: str = "Signal Stack — Company Intelligence & Executive Briefing Engine"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    # Database URL loaded securely from .env in project root
    DATABASE_URL: str

    # ---------------------------------------------------------------------------
    # Module 2: Local Ollama LLM configuration
    # Set OLLAMA_BASE_URL and OLLAMA_MODEL in your .env file.
    # No paid API keys are used. All inference runs locally via Ollama.
    # ---------------------------------------------------------------------------
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2:3b"

    # Background scheduler timezone (IANA timezone name).
    SCHEDULER_TIMEZONE: str = "Asia/Kolkata"

    # Scraper safety limits
    SCRAPER_MAX_CHARS: int = 6000       # Max characters passed to LLM after cleaning
    SCRAPER_TIMEOUT_CONNECT: int = 10   # seconds
    SCRAPER_TIMEOUT_READ: int = 20      # seconds
    SCRAPER_MAX_RETRIES: int = 2        # retries on 5xx / network error only
    SCRAPER_POLITENESS_DELAY: float = 1.0  # minimum seconds between same-domain requests
    SCRAPER_ROBOTS_CACHE_TTL_SECONDS: int = 86400  # seconds to cache robots.txt per domain (24h)

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def sync_database_url(self) -> str:
        """
        Ensures the connection string uses the psycopg driver (v3) for SQLAlchemy.
        Converts 'postgres://' or 'postgresql://' to 'postgresql+psycopg://'.
        """
        url = self.DATABASE_URL.strip()
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+psycopg://", 1)
        elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url


settings = Settings()
