from sqlalchemy import create_engine

from core.db.memory import MemoryDB


def test_memory_persists_project_checkpoint_and_observation():
    memory = MemoryDB(engine=create_engine("sqlite:///:memory:"))
    memory.remember_project("p1", "make a short", 10, "created")
    memory.remember_checkpoint("p1", "created", {"duration": 10})
    memory.remember("observation", {"message": "test"}, "p1", "obs-1")

    rows = memory.list("p1")
    types = {row["memory_type"] for row in rows}
    assert {"project", "checkpoint", "observation"}.issubset(types)
    assert any(row["content"].get("message") == "test" for row in rows)
