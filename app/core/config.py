"""
Centralized application configuration using pydantic-settings.
"""

from pathlib import Path
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

_BASE_DIR = Path(__file__).resolve().parents[2]
HTTPS = "https"
LIST_SEPARATOR = ","


def comma_list(text: str) -> frozenset[str]:
    """
    Read a comma-separated setting, ignoring case and spaces.

    :param text: e.g. ``a@x.ac.in, B@x.ac.in``.
    :type text: str
    :return: The items, lower case, empty ones dropped.
    :rtype: frozenset[str]
    """
    items = (item.strip().lower() for item in text.split(LIST_SEPARATOR))
    return frozenset(item for item in items if item)


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
    # Catalog for runs without a release. A server holds no scripts, so
    # normally there is none: no tasks until the first release.
    CATALOG_PATH: str | None = None
    # Accept releases holding readable code. Only tests turn this on: a
    # release must never put source on a server or a cluster.
    RELEASES_MAY_HOLD_SOURCE: bool = False

    # --- Computational Chemistry Driver ---
    CHEMISTRY_PYTHON_BIN: str = (
        "python3"
    )

    # --- Environment & Administration ---
    ENVIRONMENT: str = "development"  # development | staging | production
    ADMIN_API_KEY: str | None = None

    # --- Signing in with an institute account (OpenID Connect) ---
    # Unset OIDC_CLIENT_ID turns sign-in off; scripts still use keys.
    OIDC_ISSUER: str = "https://accounts.google.com"
    OIDC_CLIENT_ID: str | None = None
    OIDC_CLIENT_SECRET: str | None = None
    # Where Google sends people back, this server as browsers see it:
    # https://atomfield.<dept>.<institute>.ac.in/api/auth/callback
    OIDC_REDIRECT_URI: str | None = None
    # Comma-separated: the platform's owners. Anyone else signs in only
    # once a lab has added them.
    OWNER_EMAILS: str = ""
    SESSION_DAYS: int = 14

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
    # Each sign-in started holds a little memory in Redis for minutes.
    SIGN_IN_LIMIT_PER_MINUTE: int = 30
    # Agents asking to pair, and people typing pairing codes.
    PAIRING_LIMIT_PER_MINUTE: int = 10
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

    @property
    def owner_emails(self) -> frozenset[str]:
        """
        The people who own the platform when they sign in.

        :return: Emails, lower case.
        :rtype: frozenset[str]
        """
        return comma_list(self.OWNER_EMAILS)

    @property
    def public_origin(self) -> str | None:
        """
        This server's address as browsers see it, taken from where the
        sign-in provider sends people back.

        :return: Scheme, host and port, such as
            ``https://atomfield.example.ac.in``; None without sign-in.
        :rtype: str | None
        """
        if not self.OIDC_REDIRECT_URI:
            return None
        parts = urlsplit(self.OIDC_REDIRECT_URI)
        return f"{parts.scheme}://{parts.netloc}"

    @property
    def secure_cookies(self) -> bool:
        """
        Whether cookies are marked Secure (sent over https only): yes
        whenever browsers reach this server over https.

        :return: True for an https address.
        :rtype: bool
        """
        return urlsplit(self.OIDC_REDIRECT_URI or "").scheme == HTTPS


# Instantiate once — module-level singleton
settings = Settings()
