"""
app/core/config.py — Centralized Configuration Layer

📚 LESSON: Why pydantic-settings over os.getenv()?

    The old approach scattered os.getenv() calls across multiple files.
    If you mistyped an env var name, you'd get None silently — a silent bug.

    pydantic-settings solves this with:
    1. Type validation  → REDIS_PORT=abc → raises an error immediately at startup
    2. Single source of truth → one Settings class, imported everywhere
    3. Auto-loading from .env → no manual load_dotenv() needed
    4. IDE autocomplete → `settings.REDIS_PORT` instead of magic strings
    5. Testability → you can override settings in tests without patching os.environ

📚 LESSON: The Singleton Pattern via module-level instantiation
    `settings = Settings()` at the bottom of this file means Python instantiates
    it once when the module is first imported. Every subsequent `from app.core.config
    import settings` gets the SAME object — no re-parsing, no re-reading the file.
    This is a free singleton via Python's module import cache.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Project Identity ---
    PROJECT_NAME: str = "AtomField Execution Engine"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"

    # --- Database ---
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/atomfield_db"

    # --- Redis / Message Broker ---
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # --- Worker Tuning ---
    WORKER_MAX_JOBS: int = 10
    WORKER_JOB_TIMEOUT: int = 3600   # seconds — kill jobs exceeding 1 hour
    WORKER_KEEP_RESULT: int = 3600   # seconds — how long to cache results in Redis

    # --- Environment ---
    ENVIRONMENT: str = "development"  # development | staging | production

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # silently ignore unknown env vars (important for Docker envs)
    )


# Instantiate once — module-level singleton
settings = Settings()
