from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path
from sqlalchemy.engine import URL

DEFAULT_DB = "ai_shorts_factory"
DEFAULT_USER = "ai_shorts_factory"
DEFAULT_PORT = 5432


def find_psql() -> str | None:
    return shutil.which("psql")


def postgres_ready() -> bool:
    psql = find_psql()
    if not psql:
        return False
    try:
        return subprocess.run([psql, "--version"], capture_output=True, text=True, timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def installation_message() -> str:
    return "PostgreSQL is not installed. Run the bundled Windows bootstrap script to install an approved official distribution, then restart the application."


def database_url() -> str:
    url_env = os.getenv("YT_AUTO_DB_URL")
    if url_env:
        return url_env
    host = os.getenv("YT_AUTO_DB_HOST", "127.0.0.1")
    port_str = os.getenv("YT_AUTO_DB_PORT", str(DEFAULT_PORT))
    try:
        port = int(port_str) if port_str else DEFAULT_PORT
    except ValueError:
        port = DEFAULT_PORT
    db = os.getenv("YT_AUTO_DB_NAME", DEFAULT_DB)
    user = os.getenv("YT_AUTO_DB_USER", DEFAULT_USER)
    password = os.getenv("YT_AUTO_DB_PASSWORD", "")
    url = URL.create(
        drivername="postgresql+psycopg",
        username=user or None,
        password=password if password != "" else None,
        host=host,
        port=port,
        database=db or None,
    )
    return url.render_as_string(hide_password=False)
