"""
Utility for parsing db_connection.txt to a SQLAlchemy DSN.

The db_connection.txt is expected to contain a MySQL CLI-like string:
  mysql -u<USER> -p<PASSWORD> <DATABASE>

We convert it to a SQLAlchemy DSN like:
  mysql+pymysql://USER:PASSWORD@localhost:3306/DATABASE

Note: Host and port can be overridden via environment variables:
  DB_HOST, DB_PORT
"""

import os
from typing import Tuple


# PUBLIC_INTERFACE
def parse_mysql_cli_to_dsn(cli_line: str) -> str:
    """Parse a single mysql CLI line to a SQLAlchemy DSN string."""
    user, password, database = _extract_parts(cli_line)
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "3306")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"


def _extract_parts(cli_line: str) -> Tuple[str, str, str]:
    """Internal: extract user, password, database from mysql CLI line."""
    s = cli_line.strip()
    if not s.startswith("mysql"):
        raise ValueError("Unsupported db_connection format: expected to start with 'mysql'")

    user = None
    password = None
    database = None

    parts = s.split()
    for part in parts:
        if part.startswith("-u"):
            user = part[2:]
        elif part.startswith("-p"):
            password = part[2:]
        elif not part.startswith("-"):
            # last token typically the database
            database = part

    if not user or not database:
        raise ValueError("Missing user or database in db_connection.txt line")
    # password can be empty string technically, but we keep it as provided
    if password is None:
        password = ""

    return user, password, database
