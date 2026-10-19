"""
Centralized application configuration using pydantic-settings.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """
    Application runtime configuration loaded from environment or defaults.
    """

    # --- Project Identity ---
    PROJECT_NAME: str = "AtomField Execution Engine"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"

    # --- Database ---
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/atomfield_db"
    )

    # --- Redis / Message Broker ---
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # --- Worker Tuning ---
    WORKER_MAX_JOBS: int = 10
    WORKER_JOB_TIMEOUT: int = 3600  # seconds
    WORKER_KEEP_RESULT: int = 3600  # seconds

    # --- Workspaces and Filesystem ---
    ARTIFACTS_DIR: str = str(_BASE_DIR / "artifacts")
    HOST_SCRIPTS_DIR: str = str(_BASE_DIR / "scripts")
    HOST_ARTIFACTS_DIR: str = str(_BASE_DIR / "artifacts")

    # --- Computational Chemistry Driver ---
    CHEMISTRY_PYTHON_BIN: str = (
        "/Users/ujjawalm/atomfield-web/backend/venv/bin/python3"
    )

    # --- Environment & Administration ---
    ENVIRONMENT: str = "development"  # development | staging | production
    ADMIN_API_KEY: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Instantiate once — module-level singleton
settings = Settings()
