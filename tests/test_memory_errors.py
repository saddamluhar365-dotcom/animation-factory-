from sqlalchemy import create_engine

from core.db.memory import MemoryDB


def test_memory_error_is_persisted():
    memory = MemoryDB(engine=create_engine("sqlite:///:memory:"))
    memory.remember_error("project-1", "render", RuntimeError("render failed"))

    rows = memory.list("project-1", "observation")

    assert len(rows) == 1
    assert rows[0]["content"]["stage"] == "render"
    assert rows[0]["content"]["error"] == "render failed"
    assert rows[0]["content"]["error_type"] == "RuntimeError"
