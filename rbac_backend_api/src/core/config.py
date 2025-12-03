"""
Application configuration: environment variables, DB connection string, and JWT settings.
Reads db_connection.txt to build SQLAlchemy DSN using utils.db_conn_parser.
Also supports constructing DSN from MYSQL_* env vars (MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB).
The configuration is resilient: missing db_connection.txt will not prevent app startup.
JWT secret must be provided in production (JWT_SECRET_KEY); missing defaults are allowed only for local/dev.
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

from src.utils.db_conn_parser import parse_mysql_cli_to_dsn

# Load .env if present
load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class JWTSettings:
    """JWT configuration used by auth layer."""
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60


def _build_dsn_from_mysql_env() -> Optional[str]:
    """
    Construct a MySQL DSN from standard MYSQL_* environment variables if present.
    Expected vars (set by the database container):
      - MYSQL_HOST
      - MYSQL_PORT
      - MYSQL_USER
      - MYSQL_PASSWORD
      - MYSQL_DB
    Legacy/alt names DB_HOST/DB_PORT are also considered as fallback.
    """
    host = os.getenv("MYSQL_HOST") or os.getenv("MYSQL_URL") or os.getenv("DB_HOST") or "localhost"
    port = os.getenv("MYSQL_PORT") or os.getenv("DB_PORT") or "3306"
    user = os.getenv("MYSQL_USER")
    password = os.getenv("MYSQL_PASSWORD", "")
    database = os.getenv("MYSQL_DB")

    if user and database:
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
    return None


@dataclass
class AppSettings:
    """Application-wide settings, including database and JWT."""
    env: str
    # sql_alchemy_dsn can be None if DB is not configured yet.
    sql_alchemy_dsn: Optional[str]
    jwt: JWTSettings
    project_name: str = "RBAC Backend API"

    @staticmethod
    def _try_parse_db_file(path: str) -> Optional[str]:
        """Attempt to parse a db_connection.txt-like file into a DSN if it exists."""
        try:
            if path and os.path.exists(path):
                with open(path, "r") as f:
                    first_line = f.readline().strip()
                if first_line:
                    return parse_mysql_cli_to_dsn(first_line)
        except Exception as exc:
            logger.warning("Failed to parse DB connection file at %s: %s", path, exc)
        return None

    @staticmethod
    def from_env() -> "AppSettings":
        """
        Build settings from environment variables and db_connection.txt.

        Resolution order for SQL DSN:
          1) If DB_DSN is set in environment, use it.
          2) Else, if DB_CONNECTION_FILE env is set and file exists, parse it.
          3) Else, check default relative path to ../rbac_mysql_database/db_connection.txt and parse if exists.
          4) Else, build from MYSQL_* env vars if available.
          5) If none available, do not raise; leave DSN as None and log a clear warning.
        """
        env = os.getenv("APP_ENV", "development")

        # 1) Explicit DSN takes priority
        dsn: Optional[str] = os.getenv("DB_DSN")
        if dsn:
            try:
                safe_tail = dsn.split("@")[-1]
                logger.info("Using DB_DSN from environment (masked): mysql+pymysql://****:****@%s", safe_tail)
            except Exception:
                logger.info("Using DB_DSN from environment.")
        else:
            # 2) DB_CONNECTION_FILE if provided and exists
            db_conn_path = os.getenv("DB_CONNECTION_FILE")
            if db_conn_path:
                # Resolve relative to current working directory if not absolute.
                if not os.path.isabs(db_conn_path):
                    db_conn_path = os.path.join(os.getcwd(), db_conn_path)
                dsn = AppSettings._try_parse_db_file(db_conn_path)

            # 3) Fallback: default relative path to sibling database container folder
            if not dsn:
                default_rel = os.path.join(os.getcwd(), "..", "rbac_mysql_database", "db_connection.txt")
                dsn = AppSettings._try_parse_db_file(default_rel)

            # 4) Build from MYSQL_* env vars
            if not dsn:
                dsn = _build_dsn_from_mysql_env()
                if dsn:
                    # Log DSN minus password for observability
                    try:
                        safe_dsn = dsn.split("@")[-1]  # host:port/db
                        logger.info("DB DSN constructed from MYSQL_* envs: mysql+pymysql://****:****@%s", safe_dsn)
                    except Exception:
                        logger.info("DB DSN constructed from MYSQL_* envs.")

            # 5) If still not found, log warning and continue
            if not dsn:
                logger.warning(
                    "Database is not configured yet. Configure one of: DB_DSN, DB_CONNECTION_FILE, "
                    "../rbac_mysql_database/db_connection.txt, or MYSQL_* env vars. "
                    "The application will start, but DB-backed endpoints will fail until configured."
                )

        jwt_secret = os.getenv("JWT_SECRET_KEY", "change_me_in_env")
        if jwt_secret == "change_me_in_env":
            logger.warning("JWT_SECRET_KEY not set; using insecure default suitable for local dev only.")
        jwt_algo = os.getenv("JWT_ALGORITHM", "HS256")
        jwt_exp_minutes = int(os.getenv("JWT_ACCESS_EXPIRE_MINUTES", "60"))

        return AppSettings(
            env=env,
            sql_alchemy_dsn=dsn,
            jwt=JWTSettings(
                secret_key=jwt_secret,
                algorithm=jwt_algo,
                access_token_expire_minutes=jwt_exp_minutes,
            ),
            project_name=os.getenv("PROJECT_NAME", "RBAC Backend API"),
        )


# Singleton-like accessor
_settings: Optional[AppSettings] = None


# PUBLIC_INTERFACE
def get_settings() -> AppSettings:
    """Get cached application settings loaded from env and db_connection.txt (with MYSQL_* fallback)."""
    global _settings
    if _settings is None:
        _settings = AppSettings.from_env()
    return _settings
