"""
Application configuration: environment variables, DB connection string, and JWT settings.
Reads db_connection.txt to build SQLAlchemy DSN using utils.db_conn_parser.
"""

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

from src.utils.db_conn_parser import parse_mysql_cli_to_dsn

# Load .env if present
load_dotenv()


@dataclass
class JWTSettings:
    """JWT configuration used by auth layer."""
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60


@dataclass
class AppSettings:
    """Application-wide settings, including database and JWT."""
    env: str
    sql_alchemy_dsn: str
    jwt: JWTSettings
    project_name: str = "RBAC Backend API"

    @staticmethod
    def from_env() -> "AppSettings":
        """Build settings from environment variables and db_connection.txt."""
        env = os.getenv("APP_ENV", "development")

        # db_connection.txt should be at project root of the container unless overridden
        db_conn_path = os.getenv("DB_CONNECTION_FILE", "db_connection.txt")
        if not os.path.isabs(db_conn_path):
            # Resolve relative to container root at runtime working dir
            db_conn_path = os.path.join(os.getcwd(), db_conn_path)

        if not os.path.exists(db_conn_path):
            # Allow override via DB_DSN if provided; otherwise raise a helpful error
            override_dsn: Optional[str] = os.getenv("DB_DSN")
            if override_dsn:
                sql_alchemy_dsn = override_dsn
            else:
                raise FileNotFoundError(
                    f"db_connection.txt not found at {db_conn_path}. "
                    "Set DB_CONNECTION_FILE to override path or provide DB_DSN."
                )
        else:
            with open(db_conn_path, "r") as f:
                first_line = f.readline().strip()
            sql_alchemy_dsn = parse_mysql_cli_to_dsn(first_line)

        jwt_secret = os.getenv("JWT_SECRET_KEY", "change_me_in_env")
        jwt_algo = os.getenv("JWT_ALGORITHM", "HS256")
        jwt_exp_minutes = int(os.getenv("JWT_ACCESS_EXPIRE_MINUTES", "60"))

        return AppSettings(
            env=env,
            sql_alchemy_dsn=sql_alchemy_dsn,
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
    """Get cached application settings loaded from environment and db_connection.txt."""
    global _settings
    if _settings is None:
        _settings = AppSettings.from_env()
    return _settings
