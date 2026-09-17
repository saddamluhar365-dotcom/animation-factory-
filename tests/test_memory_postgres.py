import os

import pytest
from sqlalchemy import create_engine

from core.db.memory import MemoryDB


@pytest.mark.integration
def test_memory_postgres_roundtrip():
    url = (
        f"postgresql+psycopg://{os.environ['YT_AUTO_DB_USER']}:{os.environ['YT_AUTO_DB_PASSWORD']}"
        f"@{os.environ['YT_AUTO_DB_HOST']}:{os.environ['YT_AUTO_DB_PORT']}/{os.environ['YT_AUTO_DB_NAME']}"
    )
    memory = MemoryDB(engine=create_engine(url))
    memory.remember_project("ci-project", "integration", 5, "created")
    memory.remember("observation", {"ok": True}, "ci-project", "integration-check")
    rows = memory.list("ci-project")
    assert any(row["memory_type"] == "observation" and row["content"]["ok"] for row in rows)
