from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

from core.db.bootstrap import database_url


class MemoryDB:
    """Durable database for engine state, knowledge, decisions, artifacts and learning."""

    def __init__(self, url: str | None = None, engine: Engine | None = None):
        self._custom_engine = engine is not None
        self.engine = engine or create_engine(url or database_url(), pool_pre_ping=True, future=True)
        self._initialized = False

    @property
    def dialect(self) -> str:
        return self.engine.dialect.name

    def _create_schema(self) -> None:
        if self.dialect == "sqlite":
            statements = [
                "CREATE TABLE IF NOT EXISTS reference_profiles (id INTEGER PRIMARY KEY AUTOINCREMENT, source_url TEXT, source_hash TEXT NOT NULL, profile TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
                "CREATE TABLE IF NOT EXISTS style_dna (id INTEGER PRIMARY KEY AUTOINCREMENT, profile TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
                "CREATE TABLE IF NOT EXISTS research_items (id INTEGER PRIMARY KEY AUTOINCREMENT, source_url TEXT, title TEXT, topic TEXT, summary TEXT, evidence TEXT, retrieved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
                "CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY AUTOINCREMENT, project_key TEXT UNIQUE NOT NULL, instruction TEXT NOT NULL, duration INTEGER NOT NULL, state TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
                "CREATE TABLE IF NOT EXISTS checkpoints (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE, stage TEXT NOT NULL, payload TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
                "CREATE TABLE IF NOT EXISTS engine_memory (id INTEGER PRIMARY KEY AUTOINCREMENT, project_key TEXT NOT NULL DEFAULT '__global__', memory_type TEXT NOT NULL, memory_key TEXT NOT NULL, content TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(project_key, memory_type, memory_key))",
            ]
        else:
            statements = [
                "CREATE TABLE IF NOT EXISTS reference_profiles (id BIGSERIAL PRIMARY KEY, source_url TEXT, source_hash TEXT NOT NULL, profile JSONB NOT NULL, version INTEGER NOT NULL DEFAULT 1, created_at TIMESTAMPTZ NOT NULL DEFAULT now())",
                "CREATE TABLE IF NOT EXISTS style_dna (id BIGSERIAL PRIMARY KEY, profile JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())",
                "CREATE TABLE IF NOT EXISTS research_items (id BIGSERIAL PRIMARY KEY, source_url TEXT, title TEXT, topic TEXT, summary TEXT, evidence JSONB, retrieved_at TIMESTAMPTZ NOT NULL DEFAULT now())",
                "CREATE TABLE IF NOT EXISTS projects (id BIGSERIAL PRIMARY KEY, project_key TEXT UNIQUE NOT NULL, instruction TEXT NOT NULL, duration INTEGER NOT NULL, state JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now())",
                "CREATE TABLE IF NOT EXISTS checkpoints (id BIGSERIAL PRIMARY KEY, project_id BIGINT REFERENCES projects(id) ON DELETE CASCADE, stage TEXT NOT NULL, payload JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT now())",
                "CREATE TABLE IF NOT EXISTS engine_memory (id BIGSERIAL PRIMARY KEY, project_key TEXT NOT NULL DEFAULT '__global__', memory_type TEXT NOT NULL, memory_key TEXT NOT NULL, content JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(project_key, memory_type, memory_key))",
            ]
        with self.engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_engine_memory_project ON engine_memory(project_key)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_engine_memory_type ON engine_memory(memory_type)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_engine_memory_created ON engine_memory(created_at DESC)"))

    def initialize(self) -> None:
        if self._initialized:
            return
        try:
            self._create_schema()
            self._initialized = True
        except OperationalError:
            # Fall back to durable local SQLite if PostgreSQL is offline/unreachable and not forced
            if not self._custom_engine and self.dialect != "sqlite" and not os.getenv("CI") and os.getenv("YT_AUTO_DB_SQLITE_FALLBACK", "1") == "1":
                sqlite_path = Path(__file__).resolve().parent.parent.parent / "data" / "memory.db"
                sqlite_path.parent.mkdir(parents=True, exist_ok=True)
                self.engine = create_engine(f"sqlite:///{sqlite_path.as_posix()}", future=True)
                self._create_schema()
                self._initialized = True
            else:
                raise

    def _json(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=str)

    def _key(self, memory_type: str, content: dict[str, Any], memory_key: str | None) -> str:
        if memory_key:
            return str(memory_key)
        raw = self._json(content)
        return hashlib.sha256(f"{memory_type}\0{raw}".encode("utf-8")).hexdigest()

    def remember(self, memory_type: str, content: dict[str, Any], project_key: str | None = None, memory_key: str | None = None) -> None:
        self.initialize()
        project = project_key or "__global__"
        key = self._key(memory_type, content, memory_key)
        payload = self._json(content)
        with self.engine.begin() as conn:
            if self.dialect == "sqlite":
                conn.execute(text("""
                    INSERT INTO engine_memory(project_key, memory_type, memory_key, content)
                    VALUES (:project_key, :memory_type, :memory_key, :content)
                    ON CONFLICT(project_key, memory_type, memory_key)
                    DO UPDATE SET content=excluded.content, created_at=CURRENT_TIMESTAMP
                """), {"project_key": project, "memory_type": memory_type, "memory_key": key, "content": payload})
            else:
                conn.execute(text("""
                    INSERT INTO engine_memory(project_key, memory_type, memory_key, content)
                    VALUES (:project_key, :memory_type, :memory_key, CAST(:content AS jsonb))
                    ON CONFLICT(project_key, memory_type, memory_key)
                    DO UPDATE SET content=EXCLUDED.content, created_at=now()
                """), {"project_key": project, "memory_type": memory_type, "memory_key": key, "content": payload})

    def list(self, project_key: str | None = None, memory_type: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        self.initialize()
        clauses = []
        params: dict[str, Any] = {"limit": max(1, min(limit, 5000))}
        if project_key is not None:
            clauses.append("project_key=:project_key")
            params["project_key"] = project_key
        if memory_type is not None:
            clauses.append("memory_type=:memory_type")
            params["memory_type"] = memory_type
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.engine.begin() as conn:
            rows = conn.execute(text(f"SELECT project_key, memory_type, memory_key, content, created_at FROM engine_memory{where} ORDER BY created_at DESC LIMIT :limit"), params).mappings().all()
        result = []
        for row in rows:
            content = row["content"]
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except json.JSONDecodeError:
                    content = {"raw": content}
            result.append({"project_key": row["project_key"], "memory_type": row["memory_type"], "memory_key": row["memory_key"], "content": content, "created_at": str(row["created_at"])})
        return result

    def remember_project(self, project_key: str, instruction: str, duration: int, state: str) -> None:
        self.initialize()
        payload = self._json({"stage": state})
        with self.engine.begin() as conn:
            if self.dialect == "sqlite":
                conn.execute(text("""
                    INSERT INTO projects(project_key, instruction, duration, state) VALUES (:key,:instruction,:duration,:state)
                    ON CONFLICT(project_key) DO UPDATE SET instruction=excluded.instruction,duration=excluded.duration,state=excluded.state,updated_at=CURRENT_TIMESTAMP
                """), {"key": project_key, "instruction": instruction, "duration": duration, "state": payload})
            else:
                conn.execute(text("""
                    INSERT INTO projects(project_key,instruction,duration,state) VALUES (:key,:instruction,:duration,CAST(:state AS jsonb))
                    ON CONFLICT(project_key) DO UPDATE SET instruction=EXCLUDED.instruction,duration=EXCLUDED.duration,state=EXCLUDED.state,updated_at=now()
                """), {"key": project_key, "instruction": instruction, "duration": duration, "state": payload})
        self.remember("project", {"instruction": instruction, "duration": duration, "state": state}, project_key, "latest")

    def remember_checkpoint(self, project_key: str, stage: str, payload: dict[str, Any] | None = None) -> None:
        self.initialize()
        data = self._json(payload or {})
        with self.engine.begin() as conn:
            if self.dialect == "sqlite":
                conn.execute(text("INSERT OR IGNORE INTO projects(project_key, instruction, duration, state) VALUES (:key, 'auto-initialized', 0, '{}')"), {"key": project_key})
                conn.execute(text("INSERT INTO checkpoints(project_id,stage,payload) SELECT id,:stage,:payload FROM projects WHERE project_key=:key"), {"key": project_key, "stage": stage, "payload": data})
            else:
                conn.execute(text("INSERT INTO projects(project_key, instruction, duration, state) VALUES (:key, 'auto-initialized', 0, '{}'::jsonb) ON CONFLICT(project_key) DO NOTHING"), {"key": project_key})
                conn.execute(text("INSERT INTO checkpoints(project_id,stage,payload) SELECT id,:stage,CAST(:payload AS jsonb) FROM projects WHERE project_key=:key"), {"key": project_key, "stage": stage, "payload": data})
        self.remember("checkpoint", {"stage": stage, "payload": payload or {}}, project_key, f"{stage}:{datetime.now(timezone.utc).isoformat()}")

    def remember_plan(self, project_key: str, plan: dict[str, Any]) -> None:
        self.remember("plan", plan, project_key, "latest")
        for scene in plan.get("scenes", []):
            key = str(scene.get("index"))
            self.remember("scene", scene, project_key, key)
            for n, beat in enumerate(scene.get("beats", []), 1):
                self.remember("scene_beat", beat, project_key, f"{key}:{n}")
            for n, event in enumerate(scene.get("audio_events", []), 1):
                self.remember("audio_event", event, project_key, f"{key}:{n}")

    def remember_artifact(self, project_key: str, artifact_type: str, path: str, metadata: dict[str, Any] | None = None) -> None:
        self.remember("artifact", {"artifact_type": artifact_type, "path": path, "metadata": metadata or {}}, project_key, f"{artifact_type}:{path}")

    def remember_qc(self, project_key: str, errors: list[str], output: str | None = None) -> None:
        self.remember("qc", {"passed": not errors, "errors": errors, "output": output}, project_key, "latest")

    def remember_reference(self, profile: dict[str, Any], source_url: str | None = None, source_hash: str = "") -> None:
        self.initialize()
        source_hash = source_hash or hashlib.sha256(self._json(profile).encode("utf-8")).hexdigest()
        payload = self._json(profile)
        with self.engine.begin() as conn:
            if self.dialect == "sqlite":
                conn.execute(text("INSERT INTO reference_profiles(source_url,source_hash,profile) VALUES (:url,:hash,:profile)"), {"url": source_url, "hash": source_hash, "profile": payload})
            else:
                conn.execute(text("INSERT INTO reference_profiles(source_url,source_hash,profile) VALUES (:url,:hash,CAST(:profile AS jsonb))"), {"url": source_url, "hash": source_hash, "profile": payload})
        self.remember("reference_profile", {"source_url": source_url, "source_hash": source_hash, "profile": profile}, memory_key=source_hash)

    def remember_style_dna(self, profile: dict[str, Any]) -> None:
        self.initialize()
        payload = self._json(profile)
        with self.engine.begin() as conn:
            if self.dialect == "sqlite":
                conn.execute(text("INSERT INTO style_dna(profile) VALUES (:profile)"), {"profile": payload})
            else:
                conn.execute(text("INSERT INTO style_dna(profile) VALUES (CAST(:profile AS jsonb))"), {"profile": payload})
        self.remember("style_dna", profile, memory_key=datetime.now(timezone.utc).isoformat())

    def remember_research(self, item: dict[str, Any]) -> None:
        self.initialize()
        evidence = self._json(item.get("evidence", {}))
        with self.engine.begin() as conn:
            if self.dialect == "sqlite":
                conn.execute(text("INSERT INTO research_items(source_url,title,topic,summary,evidence) VALUES (:url,:title,:topic,:summary,:evidence)"), {"url": item.get("url"), "title": item.get("title"), "topic": item.get("topic"), "summary": item.get("summary"), "evidence": evidence})
            else:
                conn.execute(text("INSERT INTO research_items(source_url,title,topic,summary,evidence) VALUES (:url,:title,:topic,:summary,CAST(:evidence AS jsonb))"), {"url": item.get("url"), "title": item.get("title"), "topic": item.get("topic"), "summary": item.get("summary"), "evidence": evidence})
        self.remember("research", item, memory_key=str(item.get("id") or item.get("url") or item.get("title") or datetime.now(timezone.utc).isoformat()))

    def remember_learning(self, project_key: str, signal: dict[str, Any]) -> None:
        self.remember("learning", signal, project_key, str(signal.get("key") or datetime.now(timezone.utc).isoformat()))

    def remember_observation(self, project_key: str, observation: dict[str, Any]) -> None:
        self.remember("observation", observation, project_key, str(observation.get("key") or datetime.now(timezone.utc).isoformat()))

    def remember_decision(self, project_key: str, decision: dict[str, Any]) -> None:
        self.remember("decision", decision, project_key, str(decision.get("key") or datetime.now(timezone.utc).isoformat()))

    def remember_error(self, project_key: str, stage: str, error: Exception | str) -> None:
        self.remember_observation(project_key, {"key": f"error:{stage}:{datetime.now(timezone.utc).isoformat()}", "stage": stage, "error": str(error), "error_type": type(error).__name__ if isinstance(error, Exception) else "RuntimeError"})
