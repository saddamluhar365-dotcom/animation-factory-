CREATE TABLE IF NOT EXISTS reference_profiles (id BIGSERIAL PRIMARY KEY, source_url TEXT, source_hash TEXT NOT NULL, profile JSONB NOT NULL, version INTEGER NOT NULL DEFAULT 1, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS style_dna (id BIGSERIAL PRIMARY KEY, profile JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS research_items (id BIGSERIAL PRIMARY KEY, source_url TEXT, title TEXT, topic TEXT, summary TEXT, evidence JSONB, retrieved_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS projects (id BIGSERIAL PRIMARY KEY, project_key TEXT UNIQUE NOT NULL, instruction TEXT NOT NULL, duration INTEGER NOT NULL, state JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS checkpoints (id BIGSERIAL PRIMARY KEY, project_id BIGINT REFERENCES projects(id) ON DELETE CASCADE, stage TEXT NOT NULL, payload JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS idx_research_topic ON research_items(topic);
CREATE INDEX IF NOT EXISTS idx_research_retrieved ON research_items(retrieved_at DESC);
