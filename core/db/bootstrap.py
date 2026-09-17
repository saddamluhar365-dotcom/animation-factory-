from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote

DEFAULT_DB = "ai_shorts_factory"
DEFAULT_USER = "ai_shorts_factory"


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
    host = os.getenv("YT_AUTO_DB_HOST", "127.0.0.1")
    port = os.getenv("YT_AUTO_DB_PORT", "5432")
    db = os.getenv("YT_AUTO_DB_NAME", DEFAULT_DB)
    user = os.getenv("YT_AUTO_DB_USER", DEFAULT_USER)
    password = os.getenv("YT_AUTO_DB_PASSWORD", "")
    encoded_user = quote(user, safe="")
    encoded_password = quote(password, safe="")
    encoded_db = quote(db, safe="")
    return f"postgresql+psycopg://{encoded_user}:{encoded_password}@{host}:{port}/{encoded_db}"
