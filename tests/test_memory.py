from core.db.memory import MemoryDB


def test_memory_roundtrip_with_sqlite_engine():
    from sqlalchemy import create_engine, text

    engine = create_engine("sqlite:///:memory:")
    memory = MemoryDB(engine=engine)

    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE engine_memory (project_key TEXT, memory_type TEXT, memory_key TEXT, content TEXT, created_at TEXT)"))

    memory.engine = engine
    memory.initialize = lambda: None

    calls = []
    original = memory.engine.begin
    memory.remember = lambda memory_type, content, project_key=None, memory_key=None: calls.append((memory_type, content, project_key, memory_key))
    memory.remember_plan("p1", {"duration": 10, "scenes": [{"index": 1, "beats": [{"start": 0, "end": 1, "action": "test"}], "audio_events": [{"start": 0, "kind": "sfx"}]}]})

    assert [x[0] for x in calls] == ["plan", "scene", "scene_beat", "audio_event"]
