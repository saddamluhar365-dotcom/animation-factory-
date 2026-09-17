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
                "CREATE TABLE IF NOT EXISTS channel_profiles (id INTEGER PRIMARY KEY AUTOINCREMENT, handle TEXT UNIQUE NOT NULL, channel_id TEXT UNIQUE NOT NULL, uploads_playlist_id TEXT, title TEXT, description TEXT, custom_url TEXT, subscriber_count INTEGER DEFAULT 0, video_count INTEGER DEFAULT 0, auto_sync_enabled INTEGER DEFAULT 1, auto_analyze_enabled INTEGER DEFAULT 1, auto_reference_enabled INTEGER DEFAULT 1, prevent_recipe_repeats INTEGER DEFAULT 1, last_synced_at TEXT, metadata TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
                "CREATE TABLE IF NOT EXISTS channel_sync_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, channel_profile_id INTEGER REFERENCES channel_profiles(id) ON DELETE CASCADE, status TEXT NOT NULL DEFAULT 'running', videos_discovered INTEGER DEFAULT 0, videos_added INTEGER DEFAULT 0, cursor TEXT, error_message TEXT, started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, completed_at TEXT)",
                "CREATE TABLE IF NOT EXISTS channel_videos (id INTEGER PRIMARY KEY AUTOINCREMENT, channel_profile_id INTEGER REFERENCES channel_profiles(id) ON DELETE CASCADE, youtube_video_id TEXT NOT NULL, title TEXT NOT NULL, description TEXT, published_at TEXT, duration_seconds INTEGER DEFAULT 0, is_short INTEGER DEFAULT 1, video_url TEXT, thumbnail_url TEXT, etag TEXT, raw_metadata TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(channel_profile_id, youtube_video_id))",
                "CREATE TABLE IF NOT EXISTS recipe_memory (id INTEGER PRIMARY KEY AUTOINCREMENT, channel_profile_id INTEGER REFERENCES channel_profiles(id) ON DELETE CASCADE, channel_video_id INTEGER REFERENCES channel_videos(id) ON DELETE CASCADE, recipe_name TEXT NOT NULL, normalized_recipe_name TEXT NOT NULL, dish_category TEXT, cuisine TEXT, region TEXT, primary_ingredient TEXT, secondary_ingredients TEXT NOT NULL DEFAULT '[]', cooking_method TEXT, flavor_profile TEXT, environment TEXT, signatures TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(channel_profile_id, normalized_recipe_name))",
                "CREATE TABLE IF NOT EXISTS channel_dna (id INTEGER PRIMARY KEY AUTOINCREMENT, channel_profile_id INTEGER REFERENCES channel_profiles(id) ON DELETE CASCADE, dna_profile TEXT NOT NULL DEFAULT '{}', saturation_metrics TEXT NOT NULL DEFAULT '{}', version INTEGER DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(channel_profile_id))",
                "CREATE TABLE IF NOT EXISTS channel_improvement_memory (id INTEGER PRIMARY KEY AUTOINCREMENT, channel_profile_id INTEGER REFERENCES channel_profiles(id) ON DELETE CASCADE, area TEXT NOT NULL, observation TEXT NOT NULL, evidence TEXT NOT NULL DEFAULT '{}', recommendation TEXT NOT NULL, confidence REAL DEFAULT 1.0, status TEXT DEFAULT 'active', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
                "CREATE TABLE IF NOT EXISTS video_performance_memory (id INTEGER PRIMARY KEY AUTOINCREMENT, channel_video_id INTEGER REFERENCES channel_videos(id) ON DELETE CASCADE, views INTEGER DEFAULT 0, likes INTEGER DEFAULT 0, comments INTEGER DEFAULT 0, velocity_score REAL DEFAULT 0.0, retrieved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
                "CREATE TABLE IF NOT EXISTS channel_video_analyses (id INTEGER PRIMARY KEY AUTOINCREMENT, channel_profile_id INTEGER REFERENCES channel_profiles(id) ON DELETE CASCADE, channel_video_id INTEGER REFERENCES channel_videos(id) ON DELETE CASCADE, youtube_video_id TEXT NOT NULL, analysis TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(channel_profile_id, youtube_video_id))",
            ]
        else:
            statements = [
                "CREATE TABLE IF NOT EXISTS reference_profiles (id BIGSERIAL PRIMARY KEY, source_url TEXT, source_hash TEXT NOT NULL, profile JSONB NOT NULL, version INTEGER NOT NULL DEFAULT 1, created_at TIMESTAMPTZ NOT NULL DEFAULT now())",
                "CREATE TABLE IF NOT EXISTS style_dna (id BIGSERIAL PRIMARY KEY, profile JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())",
                "CREATE TABLE IF NOT EXISTS research_items (id BIGSERIAL PRIMARY KEY, source_url TEXT, title TEXT, topic TEXT, summary TEXT, evidence JSONB, retrieved_at TIMESTAMPTZ NOT NULL DEFAULT now())",
                "CREATE TABLE IF NOT EXISTS projects (id BIGSERIAL PRIMARY KEY, project_key TEXT UNIQUE NOT NULL, instruction TEXT NOT NULL, duration INTEGER NOT NULL, state JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now())",
                "CREATE TABLE IF NOT EXISTS checkpoints (id BIGSERIAL PRIMARY KEY, project_id BIGINT REFERENCES projects(id) ON DELETE CASCADE, stage TEXT NOT NULL, payload JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT now())",
                "CREATE TABLE IF NOT EXISTS engine_memory (id BIGSERIAL PRIMARY KEY, project_key TEXT NOT NULL DEFAULT '__global__', memory_type TEXT NOT NULL, memory_key TEXT NOT NULL, content JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(project_key, memory_type, memory_key))",
                "CREATE TABLE IF NOT EXISTS channel_profiles (id BIGSERIAL PRIMARY KEY, handle TEXT UNIQUE NOT NULL, channel_id TEXT UNIQUE NOT NULL, uploads_playlist_id TEXT, title TEXT, description TEXT, custom_url TEXT, subscriber_count INTEGER DEFAULT 0, video_count INTEGER DEFAULT 0, auto_sync_enabled INTEGER DEFAULT 1, auto_analyze_enabled INTEGER DEFAULT 1, auto_reference_enabled INTEGER DEFAULT 1, prevent_recipe_repeats INTEGER DEFAULT 1, last_synced_at TIMESTAMPTZ, metadata JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now())",
                "CREATE TABLE IF NOT EXISTS channel_sync_runs (id BIGSERIAL PRIMARY KEY, channel_profile_id BIGINT REFERENCES channel_profiles(id) ON DELETE CASCADE, status TEXT NOT NULL DEFAULT 'running', videos_discovered INTEGER DEFAULT 0, videos_added INTEGER DEFAULT 0, cursor TEXT, error_message TEXT, started_at TIMESTAMPTZ NOT NULL DEFAULT now(), completed_at TIMESTAMPTZ)",
                "CREATE TABLE IF NOT EXISTS channel_videos (id BIGSERIAL PRIMARY KEY, channel_profile_id BIGINT REFERENCES channel_profiles(id) ON DELETE CASCADE, youtube_video_id TEXT NOT NULL, title TEXT NOT NULL, description TEXT, published_at TIMESTAMPTZ, duration_seconds INTEGER DEFAULT 0, is_short INTEGER DEFAULT 1, video_url TEXT, thumbnail_url TEXT, etag TEXT, raw_metadata JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(channel_profile_id, youtube_video_id))",
                "CREATE TABLE IF NOT EXISTS recipe_memory (id BIGSERIAL PRIMARY KEY, channel_profile_id BIGINT REFERENCES channel_profiles(id) ON DELETE CASCADE, channel_video_id BIGINT REFERENCES channel_videos(id) ON DELETE CASCADE, recipe_name TEXT NOT NULL, normalized_recipe_name TEXT NOT NULL, dish_category TEXT, cuisine TEXT, region TEXT, primary_ingredient TEXT, secondary_ingredients JSONB NOT NULL DEFAULT '[]'::jsonb, cooking_method TEXT, flavor_profile TEXT, environment TEXT, signatures JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(channel_profile_id, normalized_recipe_name))",
                "CREATE TABLE IF NOT EXISTS channel_dna (id BIGSERIAL PRIMARY KEY, channel_profile_id BIGINT REFERENCES channel_profiles(id) ON DELETE CASCADE, dna_profile JSONB NOT NULL DEFAULT '{}'::jsonb, saturation_metrics JSONB NOT NULL DEFAULT '{}'::jsonb, version INTEGER DEFAULT 1, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(channel_profile_id))",
                "CREATE TABLE IF NOT EXISTS channel_improvement_memory (id BIGSERIAL PRIMARY KEY, channel_profile_id BIGINT REFERENCES channel_profiles(id) ON DELETE CASCADE, area TEXT NOT NULL, observation TEXT NOT NULL, evidence JSONB NOT NULL DEFAULT '{}'::jsonb, recommendation TEXT NOT NULL, confidence REAL DEFAULT 1.0, status TEXT DEFAULT 'active', created_at TIMESTAMPTZ NOT NULL DEFAULT now())",
                "CREATE TABLE IF NOT EXISTS video_performance_memory (id BIGSERIAL PRIMARY KEY, channel_video_id BIGINT REFERENCES channel_videos(id) ON DELETE CASCADE, views INTEGER DEFAULT 0, likes INTEGER DEFAULT 0, comments INTEGER DEFAULT 0, velocity_score REAL DEFAULT 0.0, retrieved_at TIMESTAMPTZ NOT NULL DEFAULT now())",
                "CREATE TABLE IF NOT EXISTS channel_video_analyses (id BIGSERIAL PRIMARY KEY, channel_profile_id BIGINT REFERENCES channel_profiles(id) ON DELETE CASCADE, channel_video_id BIGINT REFERENCES channel_videos(id) ON DELETE CASCADE, youtube_video_id TEXT NOT NULL, analysis JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(channel_profile_id, youtube_video_id))",
            ]
        with self.engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_engine_memory_project ON engine_memory(project_key)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_engine_memory_type ON engine_memory(memory_type)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_engine_memory_created ON engine_memory(created_at DESC)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_channel_videos_channel ON channel_videos(channel_profile_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_recipe_memory_norm ON recipe_memory(channel_profile_id, normalized_recipe_name)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_recipe_memory_ing ON recipe_memory(primary_ingredient)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_channel_analyses_profile ON channel_video_analyses(channel_profile_id)"))

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

    def _decode_json(self, val: Any) -> Any:
        if isinstance(val, str):
            try:
                return json.loads(val)
            except Exception:
                return val
        return val

    # -------------------------------------------------------------
    # Permanent Channel Intelligence Storage
    # -------------------------------------------------------------

    def save_channel_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        """Save or update channel profile metadata."""
        self.initialize()
        handle = str(profile.get("handle", "")).strip()
        if not handle.startswith("@") and handle and not handle.startswith("http"):
            handle = f"@{handle}"
        channel_id = str(profile.get("channel_id", "")).strip()
        uploads_playlist_id = profile.get("uploads_playlist_id") or ""
        title = profile.get("title") or ""
        description = profile.get("description") or ""
        custom_url = profile.get("custom_url") or ""
        subscriber_count = int(profile.get("subscriber_count", 0))
        video_count = int(profile.get("video_count", 0))
        auto_sync_enabled = int(bool(profile.get("auto_sync_enabled", 1)))
        auto_analyze_enabled = int(bool(profile.get("auto_analyze_enabled", 1)))
        auto_reference_enabled = int(bool(profile.get("auto_reference_enabled", 1)))
        prevent_recipe_repeats = int(bool(profile.get("prevent_recipe_repeats", 1)))
        metadata_json = self._json(profile.get("metadata", {}))

        with self.engine.begin() as conn:
            if self.dialect == "sqlite":
                conn.execute(text("""
                    INSERT INTO channel_profiles (
                        handle, channel_id, uploads_playlist_id, title, description,
                        custom_url, subscriber_count, video_count, auto_sync_enabled,
                        auto_analyze_enabled, auto_reference_enabled, prevent_recipe_repeats,
                        metadata, updated_at
                    ) VALUES (
                        :handle, :channel_id, :uploads_playlist_id, :title, :description,
                        :custom_url, :subscriber_count, :video_count, :auto_sync_enabled,
                        :auto_analyze_enabled, :auto_reference_enabled, :prevent_recipe_repeats,
                        :metadata, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT(handle) DO UPDATE SET
                        channel_id = excluded.channel_id,
                        uploads_playlist_id = CASE WHEN excluded.uploads_playlist_id != '' THEN excluded.uploads_playlist_id ELSE channel_profiles.uploads_playlist_id END,
                        title = CASE WHEN excluded.title != '' THEN excluded.title ELSE channel_profiles.title END,
                        description = CASE WHEN excluded.description != '' THEN excluded.description ELSE channel_profiles.description END,
                        custom_url = CASE WHEN excluded.custom_url != '' THEN excluded.custom_url ELSE channel_profiles.custom_url END,
                        subscriber_count = CASE WHEN excluded.subscriber_count > 0 THEN excluded.subscriber_count ELSE channel_profiles.subscriber_count END,
                        video_count = CASE WHEN excluded.video_count > 0 THEN excluded.video_count ELSE channel_profiles.video_count END,
                        auto_sync_enabled = excluded.auto_sync_enabled,
                        auto_analyze_enabled = excluded.auto_analyze_enabled,
                        auto_reference_enabled = excluded.auto_reference_enabled,
                        prevent_recipe_repeats = excluded.prevent_recipe_repeats,
                        metadata = excluded.metadata,
                        updated_at = CURRENT_TIMESTAMP
                """), {
                    "handle": handle, "channel_id": channel_id, "uploads_playlist_id": uploads_playlist_id,
                    "title": title, "description": description, "custom_url": custom_url,
                    "subscriber_count": subscriber_count, "video_count": video_count,
                    "auto_sync_enabled": auto_sync_enabled, "auto_analyze_enabled": auto_analyze_enabled,
                    "auto_reference_enabled": auto_reference_enabled, "prevent_recipe_repeats": prevent_recipe_repeats,
                    "metadata": metadata_json
                })
            else:
                conn.execute(text("""
                    INSERT INTO channel_profiles (
                        handle, channel_id, uploads_playlist_id, title, description,
                        custom_url, subscriber_count, video_count, auto_sync_enabled,
                        auto_analyze_enabled, auto_reference_enabled, prevent_recipe_repeats,
                        metadata, updated_at
                    ) VALUES (
                        :handle, :channel_id, :uploads_playlist_id, :title, :description,
                        :custom_url, :subscriber_count, :video_count, :auto_sync_enabled,
                        :auto_analyze_enabled, :auto_reference_enabled, :prevent_recipe_repeats,
                        CAST(:metadata AS jsonb), now()
                    )
                    ON CONFLICT(handle) DO UPDATE SET
                        channel_id = EXCLUDED.channel_id,
                        uploads_playlist_id = CASE WHEN EXCLUDED.uploads_playlist_id != '' THEN EXCLUDED.uploads_playlist_id ELSE channel_profiles.uploads_playlist_id END,
                        title = CASE WHEN EXCLUDED.title != '' THEN EXCLUDED.title ELSE channel_profiles.title END,
                        description = CASE WHEN EXCLUDED.description != '' THEN EXCLUDED.description ELSE channel_profiles.description END,
                        custom_url = CASE WHEN EXCLUDED.custom_url != '' THEN EXCLUDED.custom_url ELSE channel_profiles.custom_url END,
                        subscriber_count = CASE WHEN EXCLUDED.subscriber_count > 0 THEN EXCLUDED.subscriber_count ELSE channel_profiles.subscriber_count END,
                        video_count = CASE WHEN EXCLUDED.video_count > 0 THEN EXCLUDED.video_count ELSE channel_profiles.video_count END,
                        auto_sync_enabled = EXCLUDED.auto_sync_enabled,
                        auto_analyze_enabled = EXCLUDED.auto_analyze_enabled,
                        auto_reference_enabled = EXCLUDED.auto_reference_enabled,
                        prevent_recipe_repeats = EXCLUDED.prevent_recipe_repeats,
                        metadata = EXCLUDED.metadata,
                        updated_at = now()
                """), {
                    "handle": handle, "channel_id": channel_id, "uploads_playlist_id": uploads_playlist_id,
                    "title": title, "description": description, "custom_url": custom_url,
                    "subscriber_count": subscriber_count, "video_count": video_count,
                    "auto_sync_enabled": auto_sync_enabled, "auto_analyze_enabled": auto_analyze_enabled,
                    "auto_reference_enabled": auto_reference_enabled, "prevent_recipe_repeats": prevent_recipe_repeats,
                    "metadata": metadata_json
                })

        res = self.get_channel_profile(handle=handle)
        return res or {}

    def get_channel_profile(self, handle: str | None = None, channel_id: str | None = None, profile_id: int | None = None) -> dict[str, Any] | None:
        """Get channel profile by handle, channel_id, profile_id, or return the latest active profile."""
        self.initialize()
        clauses = []
        params: dict[str, Any] = {}
        if profile_id is not None:
            clauses.append("id = :profile_id")
            params["profile_id"] = profile_id
        elif handle:
            h = handle.strip()
            if not h.startswith("@") and not h.startswith("http"):
                h_alt = f"@{h}"
                clauses.append("(handle = :handle OR handle = :h_alt)")
                params["handle"] = h
                params["h_alt"] = h_alt
            else:
                clauses.append("handle = :handle")
                params["handle"] = h
        elif channel_id:
            clauses.append("channel_id = :channel_id")
            params["channel_id"] = channel_id

        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        query = f"SELECT * FROM channel_profiles{where} ORDER BY updated_at DESC LIMIT 1"
        with self.engine.begin() as conn:
            row = conn.execute(text(query), params).mappings().first()
        if not row:
            return None
        res = dict(row)
        res["metadata"] = self._decode_json(res.get("metadata"))
        return res

    def list_channel_profiles(self) -> list[dict[str, Any]]:
        self.initialize()
        with self.engine.begin() as conn:
            rows = conn.execute(text("SELECT * FROM channel_profiles ORDER BY updated_at DESC")).mappings().all()
        result = []
        for r in rows:
            d = dict(r)
            d["metadata"] = self._decode_json(d.get("metadata"))
            result.append(d)
        return result

    def update_channel_settings(self, profile_id: int, **settings: Any) -> None:
        self.initialize()
        if not settings:
            return
        fields = []
        params: dict[str, Any] = {"id": profile_id}
        allowed = {
            "auto_sync_enabled", "auto_analyze_enabled", "auto_reference_enabled",
            "prevent_recipe_repeats", "last_synced_at", "video_count", "subscriber_count"
        }
        for k, v in settings.items():
            if k in allowed:
                fields.append(f"{k} = :{k}")
                params[k] = int(v) if isinstance(v, bool) else v
        if not fields:
            return
        sql = f"UPDATE channel_profiles SET {', '.join(fields)} WHERE id = :id"
        with self.engine.begin() as conn:
            conn.execute(text(sql), params)

    def record_sync_run(self, channel_profile_id: int, status: str = "running", videos_discovered: int = 0, videos_added: int = 0, cursor: str | None = None, error_message: str | None = None, run_id: int | None = None) -> int:
        self.initialize()
        with self.engine.begin() as conn:
            if run_id:
                completed = "CURRENT_TIMESTAMP" if self.dialect == "sqlite" else "now()"
                conn.execute(text(f"""
                    UPDATE channel_sync_runs SET status = :status, videos_discovered = :discovered,
                    videos_added = :added, cursor = :cursor, error_message = :err, completed_at = {completed}
                    WHERE id = :run_id
                """), {"status": status, "discovered": videos_discovered, "added": videos_added, "cursor": cursor, "err": error_message, "run_id": run_id})
                return run_id
            else:
                if self.dialect == "sqlite":
                    cursor_res = conn.execute(text("""
                        INSERT INTO channel_sync_runs (channel_profile_id, status, videos_discovered, videos_added, cursor, error_message)
                        VALUES (:cid, :status, :discovered, :added, :cursor, :err)
                    """), {"cid": channel_profile_id, "status": status, "discovered": videos_discovered, "added": videos_added, "cursor": cursor, "err": error_message})
                    return cursor_res.lastrowid or 0
                else:
                    cursor_res = conn.execute(text("""
                        INSERT INTO channel_sync_runs (channel_profile_id, status, videos_discovered, videos_added, cursor, error_message)
                        VALUES (:cid, :status, :discovered, :added, :cursor, :err) RETURNING id
                    """), {"cid": channel_profile_id, "status": status, "discovered": videos_discovered, "added": videos_added, "cursor": cursor, "err": error_message})
                    row = cursor_res.first()
                    return row[0] if row else 0

    def save_channel_videos(self, channel_profile_id: int, videos: list[dict[str, Any]]) -> int:
        self.initialize()
        if not videos:
            return 0
        added = 0
        with self.engine.begin() as conn:
            existing_rows = conn.execute(
                text("SELECT youtube_video_id FROM channel_videos WHERE channel_profile_id = :cid"),
                {"cid": channel_profile_id},
            ).fetchall()
            existing_ids = {r[0] for r in existing_rows}

            for v in videos:
                vid = str(v.get("youtube_video_id") or v.get("id") or "").strip()
                if not vid:
                    continue
                is_new = vid not in existing_ids
                title = str(v.get("title") or "")
                desc = str(v.get("description") or "")
                published_at = v.get("published_at")
                duration = int(v.get("duration_seconds") or 0)
                is_short = int(bool(v.get("is_short", True)))
                video_url = v.get("video_url") or f"https://www.youtube.com/watch?v={vid}"
                thumbnail_url = v.get("thumbnail_url") or ""
                etag = v.get("etag") or ""
                raw_meta = self._json(v.get("raw_metadata") or {})

                if self.dialect == "sqlite":
                    conn.execute(text("""
                        INSERT INTO channel_videos (
                            channel_profile_id, youtube_video_id, title, description,
                            published_at, duration_seconds, is_short, video_url, thumbnail_url,
                            etag, raw_metadata
                        ) VALUES (
                            :cid, :vid, :title, :desc, :published_at, :duration, :is_short,
                            :video_url, :thumb, :etag, :meta
                        )
                        ON CONFLICT(channel_profile_id, youtube_video_id) DO UPDATE SET
                            title = excluded.title,
                            description = excluded.description,
                            duration_seconds = excluded.duration_seconds,
                            is_short = excluded.is_short,
                            thumbnail_url = excluded.thumbnail_url,
                            raw_metadata = excluded.raw_metadata
                    """), {
                        "cid": channel_profile_id, "vid": vid, "title": title, "desc": desc,
                        "published_at": published_at, "duration": duration, "is_short": is_short,
                        "video_url": video_url, "thumb": thumbnail_url, "etag": etag, "meta": raw_meta
                    })
                else:
                    conn.execute(text("""
                        INSERT INTO channel_videos (
                            channel_profile_id, youtube_video_id, title, description,
                            published_at, duration_seconds, is_short, video_url, thumbnail_url,
                            etag, raw_metadata
                        ) VALUES (
                            :cid, :vid, :title, :desc, :published_at, :duration, :is_short,
                            :video_url, :thumb, :etag, CAST(:meta AS jsonb)
                        )
                        ON CONFLICT(channel_profile_id, youtube_video_id) DO UPDATE SET
                            title = EXCLUDED.title,
                            description = EXCLUDED.description,
                            duration_seconds = EXCLUDED.duration_seconds,
                            is_short = EXCLUDED.is_short,
                            thumbnail_url = EXCLUDED.thumbnail_url,
                            raw_metadata = EXCLUDED.raw_metadata
                    """), {
                        "cid": channel_profile_id, "vid": vid, "title": title, "desc": desc,
                        "published_at": published_at, "duration": duration, "is_short": is_short,
                        "video_url": video_url, "thumb": thumbnail_url, "etag": etag, "meta": raw_meta
                    })
                if is_new:
                    added += 1
                    existing_ids.add(vid)

            now_str = datetime.now(timezone.utc).isoformat()
            conn.execute(text("""
                UPDATE channel_profiles
                SET video_count = (SELECT COUNT(*) FROM channel_videos WHERE channel_profile_id = :cid),
                    last_synced_at = :now
                WHERE id = :cid
            """), {"cid": channel_profile_id, "now": now_str})

        return added

    def get_channel_videos(self, channel_profile_id: int, only_shorts: bool = False, limit: int = 500) -> list[dict[str, Any]]:
        self.initialize()
        clauses = ["channel_profile_id = :cid"]
        params: dict[str, Any] = {"cid": channel_profile_id, "limit": limit}
        if only_shorts:
            clauses.append("is_short = 1")
        where = " WHERE " + " AND ".join(clauses)
        sql = f"SELECT * FROM channel_videos{where} ORDER BY published_at DESC LIMIT :limit"
        with self.engine.begin() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
        results = []
        for r in rows:
            d = dict(r)
            d["raw_metadata"] = self._decode_json(d.get("raw_metadata"))
            results.append(d)
        return results

    def get_unextracted_channel_videos(self, channel_profile_id: int, limit: int = 500) -> list[dict[str, Any]]:
        """Get channel videos that have not yet had culinary intelligence extracted into recipe_memory."""
        self.initialize()
        sql = """
            SELECT v.* FROM channel_videos v
            WHERE v.channel_profile_id = :cid
              AND v.id NOT IN (
                  SELECT channel_video_id FROM recipe_memory
                  WHERE channel_profile_id = :cid AND channel_video_id IS NOT NULL
              )
            ORDER BY v.published_at DESC LIMIT :limit
        """
        with self.engine.begin() as conn:
            rows = conn.execute(text(sql), {"cid": channel_profile_id, "limit": limit}).mappings().all()
        results = []
        for r in rows:
            d = dict(r)
            d["raw_metadata"] = self._decode_json(d.get("raw_metadata"))
            results.append(d)
        return results

    def save_recipe_record(self, record: dict[str, Any]) -> int:
        self.initialize()
        cid = int(record["channel_profile_id"])
        vid = record.get("channel_video_id")
        name = str(record.get("recipe_name", "")).strip()
        norm = str(record.get("normalized_recipe_name", "")).strip().lower()
        if not norm:
            norm = name.lower()
        dish_category = record.get("dish_category") or ""
        cuisine = record.get("cuisine") or ""
        region = record.get("region") or ""
        primary_ing = str(record.get("primary_ingredient") or "").strip().lower()
        secondary_ings = self._json(record.get("secondary_ingredients") or [])
        method = record.get("cooking_method") or ""
        flavor = record.get("flavor_profile") or ""
        env = record.get("environment") or ""
        sigs = self._json(record.get("signatures") or {})

        with self.engine.begin() as conn:
            if self.dialect == "sqlite":
                res = conn.execute(text("""
                    INSERT INTO recipe_memory (
                        channel_profile_id, channel_video_id, recipe_name, normalized_recipe_name,
                        dish_category, cuisine, region, primary_ingredient, secondary_ingredients,
                        cooking_method, flavor_profile, environment, signatures
                    ) VALUES (
                        :cid, :vid, :name, :norm, :dish, :cuisine, :region, :primary_ing,
                        :secondary_ings, :method, :flavor, :env, :sigs
                    )
                    ON CONFLICT(channel_profile_id, normalized_recipe_name) DO UPDATE SET
                        recipe_name = excluded.recipe_name,
                        dish_category = excluded.dish_category,
                        cuisine = excluded.cuisine,
                        region = excluded.region,
                        primary_ingredient = excluded.primary_ingredient,
                        secondary_ingredients = excluded.secondary_ingredients,
                        cooking_method = excluded.cooking_method,
                        flavor_profile = excluded.flavor_profile,
                        environment = excluded.environment,
                        signatures = excluded.signatures
                """), {
                    "cid": cid, "vid": vid, "name": name, "norm": norm, "dish": dish_category,
                    "cuisine": cuisine, "region": region, "primary_ing": primary_ing,
                    "secondary_ings": secondary_ings, "method": method, "flavor": flavor,
                    "env": env, "sigs": sigs
                })
                return res.lastrowid or 0
            else:
                res = conn.execute(text("""
                    INSERT INTO recipe_memory (
                        channel_profile_id, channel_video_id, recipe_name, normalized_recipe_name,
                        dish_category, cuisine, region, primary_ingredient, secondary_ingredients,
                        cooking_method, flavor_profile, environment, signatures
                    ) VALUES (
                        :cid, :vid, :name, :norm, :dish, :cuisine, :region, :primary_ing,
                        CAST(:secondary_ings AS jsonb), :method, :flavor, :env, CAST(:sigs AS jsonb)
                    )
                    ON CONFLICT(channel_profile_id, normalized_recipe_name) DO UPDATE SET
                        recipe_name = EXCLUDED.recipe_name,
                        dish_category = EXCLUDED.dish_category,
                        cuisine = EXCLUDED.cuisine,
                        region = EXCLUDED.region,
                        primary_ingredient = EXCLUDED.primary_ingredient,
                        secondary_ingredients = EXCLUDED.secondary_ingredients,
                        cooking_method = EXCLUDED.cooking_method,
                        flavor_profile = EXCLUDED.flavor_profile,
                        environment = EXCLUDED.environment,
                        signatures = EXCLUDED.signatures
                    RETURNING id
                """), {
                    "cid": cid, "vid": vid, "name": name, "norm": norm, "dish": dish_category,
                    "cuisine": cuisine, "region": region, "primary_ing": primary_ing,
                    "secondary_ings": secondary_ings, "method": method, "flavor": flavor,
                    "env": env, "sigs": sigs
                })
                row = res.first()
                return row[0] if row else 0

    def get_recipes(self, channel_profile_id: int) -> list[dict[str, Any]]:
        self.initialize()
        sql = "SELECT * FROM recipe_memory WHERE channel_profile_id = :cid ORDER BY created_at DESC"
        with self.engine.begin() as conn:
            rows = conn.execute(text(sql), {"cid": channel_profile_id}).mappings().all()
        res = []
        for r in rows:
            d = dict(r)
            d["secondary_ingredients"] = self._decode_json(d.get("secondary_ingredients"))
            d["signatures"] = self._decode_json(d.get("signatures"))
            res.append(d)
        return res

    def save_channel_dna(self, channel_profile_id: int, dna_profile: dict[str, Any], saturation_metrics: dict[str, Any] | None = None) -> None:
        self.initialize()
        dna_json = self._json(dna_profile)
        sat_json = self._json(saturation_metrics or {})
        with self.engine.begin() as conn:
            if self.dialect == "sqlite":
                conn.execute(text("""
                    INSERT INTO channel_dna (channel_profile_id, dna_profile, saturation_metrics, updated_at)
                    VALUES (:cid, :dna, :sat, CURRENT_TIMESTAMP)
                    ON CONFLICT(channel_profile_id) DO UPDATE SET
                        dna_profile = excluded.dna_profile,
                        saturation_metrics = excluded.saturation_metrics,
                        updated_at = CURRENT_TIMESTAMP
                """), {"cid": channel_profile_id, "dna": dna_json, "sat": sat_json})
            else:
                conn.execute(text("""
                    INSERT INTO channel_dna (channel_profile_id, dna_profile, saturation_metrics, updated_at)
                    VALUES (:cid, CAST(:dna AS jsonb), CAST(:sat AS jsonb), now())
                    ON CONFLICT(channel_profile_id) DO UPDATE SET
                        dna_profile = EXCLUDED.dna_profile,
                        saturation_metrics = EXCLUDED.saturation_metrics,
                        updated_at = now()
                """), {"cid": channel_profile_id, "dna": dna_json, "sat": sat_json})

    def get_channel_dna(self, channel_profile_id: int) -> dict[str, Any] | None:
        self.initialize()
        with self.engine.begin() as conn:
            row = conn.execute(text("SELECT * FROM channel_dna WHERE channel_profile_id = :cid"), {"cid": channel_profile_id}).mappings().first()
        if not row:
            return None
        d = dict(row)
        d["dna_profile"] = self._decode_json(d.get("dna_profile"))
        d["saturation_metrics"] = self._decode_json(d.get("saturation_metrics"))
        return d

    def save_improvement_signal(self, channel_profile_id: int, signal: dict[str, Any]) -> None:
        self.initialize()
        area = signal.get("area") or "general"
        obs = signal.get("observation") or ""
        evidence = self._json(signal.get("evidence") or {})
        rec = signal.get("recommendation") or ""
        conf = float(signal.get("confidence", 1.0))
        status = signal.get("status") or "active"
        with self.engine.begin() as conn:
            if self.dialect == "sqlite":
                conn.execute(text("""
                    INSERT INTO channel_improvement_memory (channel_profile_id, area, observation, evidence, recommendation, confidence, status)
                    VALUES (:cid, :area, :obs, :evidence, :rec, :conf, :status)
                """), {"cid": channel_profile_id, "area": area, "obs": obs, "evidence": evidence, "rec": rec, "conf": conf, "status": status})
            else:
                conn.execute(text("""
                    INSERT INTO channel_improvement_memory (channel_profile_id, area, observation, evidence, recommendation, confidence, status)
                    VALUES (:cid, :area, :obs, CAST(:evidence AS jsonb), :rec, :conf, :status)
                """), {"cid": channel_profile_id, "area": area, "obs": obs, "evidence": evidence, "rec": rec, "conf": conf, "status": status})

    def get_improvement_signals(self, channel_profile_id: int, active_only: bool = True) -> list[dict[str, Any]]:
        self.initialize()
        where = "WHERE channel_profile_id = :cid"
        params: dict[str, Any] = {"cid": channel_profile_id}
        if active_only:
            where += " AND status = 'active'"
        sql = f"SELECT * FROM channel_improvement_memory {where} ORDER BY created_at DESC"
        with self.engine.begin() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
        res = []
        for r in rows:
            d = dict(r)
            d["evidence"] = self._decode_json(d.get("evidence"))
            res.append(d)
        return res

    def save_video_performance(self, channel_video_id: int, performance: dict[str, Any]) -> None:
        self.initialize()
        views = int(performance.get("views", 0))
        likes = int(performance.get("likes", 0))
        comments = int(performance.get("comments", 0))
        velocity = float(performance.get("velocity_score", 0.0))
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO video_performance_memory (channel_video_id, views, likes, comments, velocity_score)
                VALUES (:vid, :views, :likes, :comments, :velocity)
            """), {"vid": channel_video_id, "views": views, "likes": likes, "comments": comments, "velocity": velocity})

    def get_channel_stats(self, channel_profile_id: int) -> dict[str, Any]:
        self.initialize()
        with self.engine.begin() as conn:
            v_count = conn.execute(text("SELECT COUNT(*) FROM channel_videos WHERE channel_profile_id = :cid"), {"cid": channel_profile_id}).scalar() or 0
            s_count = conn.execute(text("SELECT COUNT(*) FROM channel_videos WHERE channel_profile_id = :cid AND is_short = 1"), {"cid": channel_profile_id}).scalar() or 0
            r_count = conn.execute(text("SELECT COUNT(*) FROM recipe_memory WHERE channel_profile_id = :cid"), {"cid": channel_profile_id}).scalar() or 0
            a_count = conn.execute(text("SELECT COUNT(*) FROM channel_video_analyses WHERE channel_profile_id = :cid"), {"cid": channel_profile_id}).scalar() or 0
            has_dna = bool(conn.execute(text("SELECT 1 FROM channel_dna WHERE channel_profile_id = :cid LIMIT 1"), {"cid": channel_profile_id}).scalar())
            profile = conn.execute(text("SELECT last_synced_at, title, handle, uploads_playlist_id FROM channel_profiles WHERE id = :cid"), {"cid": channel_profile_id}).mappings().first()

        return {
            "channel_profile_id": channel_profile_id,
            "handle": profile["handle"] if profile else "",
            "title": profile["title"] if profile else "",
            "uploads_playlist_id": profile["uploads_playlist_id"] if profile else "",
            "last_synced_at": str(profile["last_synced_at"]) if profile and profile["last_synced_at"] else None,
            "video_count": v_count,
            "shorts_count": s_count,
            "recipe_count": r_count,
            "analyzed_shorts_count": a_count,
            "has_dna": has_dna,
        }

    def save_video_analysis(
        self,
        channel_profile_id: int,
        channel_video_id: int | None,
        youtube_video_id: str,
        analysis: dict[str, Any],
    ) -> int:
        self.initialize()
        cid = int(channel_profile_id)
        vid = channel_video_id
        yt_id = str(youtube_video_id).strip()
        analysis_json = self._json(analysis)

        with self.engine.begin() as conn:
            if self.dialect == "sqlite":
                res = conn.execute(text("""
                    INSERT INTO channel_video_analyses (
                        channel_profile_id, channel_video_id, youtube_video_id, analysis, created_at
                    ) VALUES (
                        :cid, :vid, :yt_id, :analysis, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT(channel_profile_id, youtube_video_id) DO UPDATE SET
                        channel_video_id = CASE WHEN excluded.channel_video_id IS NOT NULL THEN excluded.channel_video_id ELSE channel_video_analyses.channel_video_id END,
                        analysis = excluded.analysis,
                        created_at = CURRENT_TIMESTAMP
                """), {"cid": cid, "vid": vid, "yt_id": yt_id, "analysis": analysis_json})
                return res.lastrowid or 0
            else:
                res = conn.execute(text("""
                    INSERT INTO channel_video_analyses (
                        channel_profile_id, channel_video_id, youtube_video_id, analysis, created_at
                    ) VALUES (
                        :cid, :vid, :yt_id, CAST(:analysis AS jsonb), now()
                    )
                    ON CONFLICT(channel_profile_id, youtube_video_id) DO UPDATE SET
                        channel_video_id = CASE WHEN EXCLUDED.channel_video_id IS NOT NULL THEN EXCLUDED.channel_video_id ELSE channel_video_analyses.channel_video_id END,
                        analysis = EXCLUDED.analysis,
                        created_at = now()
                    RETURNING id
                """), {"cid": cid, "vid": vid, "yt_id": yt_id, "analysis": analysis_json})
                row = res.first()
                return row[0] if row else 0

    def get_video_analyses(self, channel_profile_id: int, limit: int = 10) -> list[dict[str, Any]]:
        self.initialize()
        sql = "SELECT * FROM channel_video_analyses WHERE channel_profile_id = :cid ORDER BY created_at DESC LIMIT :limit"
        with self.engine.begin() as conn:
            rows = conn.execute(text(sql), {"cid": channel_profile_id, "limit": limit}).mappings().all()
        results = []
        for r in rows:
            d = dict(r)
            d["analysis"] = self._decode_json(d.get("analysis"))
            results.append(d)
        return results

