from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from core.db.bootstrap import database_url


class MemoryDB:
    """Durable PostgreSQL memory for every important engine artifact and event."""

    def __init__(self, url: str | None = None, engine: Engine | None = None):
        self.engine = engine or create_engine(url or database_url(), pool_pre_ping=True, future=True)

    def initialize(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS engine_memory (
            id BIGSERIAL PRIMARY KEY,
            project_key TEXT,
            memory_type TEXT NOT NULL,
            memory_key TEXT,
            content JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(project_key, memory_type, memory_key)
        );
        CREATE INDEX IF NOT EXISTS idx_engine_memory_project ON engine_memory(project_key);
        CREATE INDEX IF NOT EXISTS idx_engine_memory_type ON engine_memory(memory_type);
        CREATE INDEX IF NOT EXISTS idx_engine_memory_created ON engine_memory(created_at DESC);
        """
        with self.engine.begin() as conn:
            for statement in schema.split(";"):
                if statement.strip():
                    conn.execute(text(statement))

    def remember(self, memory_type: str, content: dict[str, Any], project_key: str | None = None, memory_key: str | None = None) -> None:
        self.initialize()
        payload = json.dumps(content, ensure_ascii=False, default=str)
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO engine_memory(project_key, memory_type, memory_key, content)
                    VALUES (:project_key, :memory_type, :memory_key, CAST(:content AS jsonb))
                    ON CONFLICT(project_key, memory_type, memory_key)
                    DO UPDATE SET content = EXCLUDED.content, created_at = now()
                """),
                {"project_key": project_key, "memory_type": memory_type, "memory_key": memory_key, "content": payload},
            )

    def remember_project(self, project_key: str, instruction: str, duration: int, state: str) -> None:
        self.initialize()
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO projects(project_key, instruction, duration, state)
                VALUES (:key, :instruction, :duration, CAST(:state AS jsonb))
                ON CONFLICT(project_key) DO UPDATE SET instruction=EXCLUDED.instruction,
                    duration=EXCLUDED.duration, state=EXCLUDED.state, updated_at=now()
            """), {"key": project_key, "instruction": instruction, "duration": duration, "state": json.dumps({"stage": state})})

    def remember_checkpoint(self, project_key: str, stage: str, payload: dict[str, Any] | None = None) -> None:
        self.initialize()
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO checkpoints(project_id, stage, payload)
                SELECT id, :stage, CAST(:payload AS jsonb) FROM projects WHERE project_key=:key
            """), {"key": project_key, "stage": stage, "payload": json.dumps(payload or {}, ensure_ascii=False, default=str)})
        self.remember("checkpoint", {"stage": stage, "payload": payload or {}}, project_key, stage)

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
        self.remember("artifact", {"artifact_type": artifact_type, "path": path, "metadata": metadata or {}}, project_key, artifact_type)

    def remember_qc(self, project_key: str, errors: list[str], output: str | None = None) -> None:
        self.remember("qc", {"passed": not errors, "errors": errors, "output": output}, project_key, "latest")

    def remember_reference(self, profile: dict[str, Any], source_url: str | None = None, source_hash: str = "") -> None:
        self.initialize()
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO reference_profiles(source_url, source_hash, profile)
                VALUES (:url, :hash, CAST(:profile AS jsonb))
            """), {"url": source_url, "hash": source_hash or "unknown", "profile": json.dumps(profile, ensure_ascii=False, default=str)})
        self.remember("reference_profile", {"source_url": source_url, "source_hash": source_hash, "profile": profile}, memory_key=source_hash or source_url or "latest")

    def remember_research(self, item: dict[str, Any]) -> None:
        self.initialize()
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO research_items(source_url, title, topic, summary, evidence)
                VALUES (:url, :title, :topic, :summary, CAST(:evidence AS jsonb))
            """), {
                "url": item.get("url"), "title": item.get("title"), "topic": item.get("topic"),
                "summary": item.get("summary"), "evidence": json.dumps(item.get("evidence", {}), ensure_ascii=False, default=str),
            })
        self.remember("research", item, memory_key=str(item.get("id") or item.get("url") or item.get("title") or datetime.now(timezone.utc).isoformat()))

    def remember_learning(self, project_key: str, signal: dict[str, Any]) -> None:
        self.remember("learning", signal, project_key, str(signal.get("key") or datetime.now(timezone.utc).isoformat()))

    def remember_observation(self, project_key: str, observation: dict[str, Any]) -> None:
        self.remember("observation", observation, project_key, str(observation.get("key") or datetime.now(timezone.utc).isoformat()))

    def remember_decision(self, project_key: str, decision: dict[str, Any]) -> None:
        self.remember("decision", decision, project_key, str(decision.get("key") or datetime.now(timezone.utc).isoformat()))
