import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from core.db.bootstrap import database_url
from core.db.memory import MemoryDB


@pytest.mark.integration
def test_memory_postgres_roundtrip():
    if not os.environ.get("YT_AUTO_DB_HOST") and not os.environ.get("YT_AUTO_DB_URL"):
        pytest.skip("PostgreSQL environment not configured (set YT_AUTO_DB_HOST or YT_AUTO_DB_URL)")

    url = database_url()
    try:
        engine = create_engine(url, pool_pre_ping=True)
        memory = MemoryDB(engine=engine)
        memory.remember_project("ci-project", "integration", 5, "created")
        memory.remember("observation", {"ok": True}, "ci-project", "integration-check")
        rows = memory.list("ci-project")
        assert any(row["memory_type"] == "observation" and row["content"]["ok"] for row in rows)
    except OperationalError as exc:
        if not os.environ.get("CI"):
            pytest.skip(f"PostgreSQL not reachable or credentials refused in local environment: {exc}")
        raise
