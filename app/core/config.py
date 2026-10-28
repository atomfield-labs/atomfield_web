"""
Centralized application configuration using pydantic-settings.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

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
    # Same names as the official postgres image uses, so one .env file
    # configures both the database container and the application.
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "atomfield_db"

    # --- Database backups (taken before pending migrations run) ---
    BACKUP_DIR: str = str(_BASE_DIR / "backups")
    BACKUP_KEEP: int = 10
    # Escape hatch for machines without pg_dump; never set in production.
    SKIP_DB_BACKUP: bool = False

    # --- Redis / Message Broker ---
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str | None = None
    # Logical database index; tests use their own so a flush never
    # touches development data.
    REDIS_DB: int = 0

    # --- Worker Tuning ---
    WORKER_MAX_JOBS: int = 10
    WORKER_JOB_TIMEOUT: int = 3600  # seconds
    WORKER_KEEP_RESULT: int = 3600  # seconds

    # --- Workspaces and Filesystem ---
    ARTIFACTS_DIR: str = str(_BASE_DIR / "artifacts")
    # Files kept by the server: uploads, UI files, run zips.
    STORAGE_DIR: str = str(_BASE_DIR / "storage")
    # Signs storage links; the same value in every API process.
    STORAGE_SIGNING_KEY: str | None = None
    # Largest run zip uploaded, and how long a zip is kept.
    BUNDLE_MAX_BYTES: int = 1024**3
    BUNDLE_KEEP_DAYS: int = 7

    # --- Task catalog, written by the domain pack (afscripts) ---
    CATALOG_PATH: str = str(_BASE_DIR / "scripts_repo" / "catalog.json")

    # --- Computational Chemistry Driver ---
    CHEMISTRY_PYTHON_BIN: str = (
        "python3"
    )

    # --- Environment & Administration ---
    ENVIRONMENT: str = "development"  # development | staging | production
    ADMIN_API_KEY: str | None = None

    # --- Agents ---
    # Token of the platform's own (house) agent; None disables it.
    HOUSE_AGENT_TOKEN: str | None = None

    # --- Sweeper (repairs queues and expired leases) ---
    SWEEPER_ENABLED: bool = True
    SWEEP_INTERVAL_SECONDS: float = 30.0
    # An agent silent this long has lost its jobs.
    LEASE_TIMEOUT_SECONDS: float = 180.0
    # Jobs a cluster scheduler keeps running without their agent: wait
    # a day for a crashed agent to come back before giving up.
    SCHEDULED_LEASE_TIMEOUT_SECONDS: float = 24 * 3600.0
    DEADLINE_GRACE_SECONDS: float = 600.0

    # --- Abuse limits ---
    KEY_CREATION_LIMIT_PER_HOUR: int = 3
    # True only behind Cloudflare Tunnel with the API port closed to the
    # internet; otherwise anyone could forge CF-Connecting-IP.
    TRUST_PROXY_HEADERS: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        """
        Assemble the async SQLAlchemy URL from the connection parts.

        ``URL.create`` escapes the password, so characters such as ``@``
        or ``/`` in a strong password cannot corrupt the URL.

        :return: URL for ``create_async_engine``, password included.
        :rtype: str
        """
        url = URL.create(
            drivername="postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        )
        return url.render_as_string(hide_password=False)


# Instantiate once — module-level singleton
settings = Settings()
