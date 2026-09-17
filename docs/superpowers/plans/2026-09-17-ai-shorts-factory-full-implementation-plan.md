# AI Shorts Factory Full Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current Windows-first prototype into a production-oriented YouTube Shorts factory implementing the approved reference intelligence, research memory, provider routing, PostgreSQL persistence, image-first animation, audio sync, strict QC, recovery, offline mode, and secure setup flow.

**Architecture:** Keep the desktop UI thin and move orchestration into focused core modules. Cloud providers handle heavy intelligence/image generation while the local machine owns persistence, deterministic timeline construction, image animation, audio assembly, QC and FFmpeg rendering. PostgreSQL stores structured state/intelligence while media stays in local asset directories and secrets remain in an encrypted vault.

**Tech Stack:** Python 3.12, Tkinter/CustomTkinter-compatible desktop UI, PostgreSQL, SQLAlchemy/psycopg, FFmpeg/ffprobe, HTTP clients, pytest, encrypted local secret storage, provider adapters.

**Spec:** `docs/superpowers/specs/2026-09-17-ai-shorts-factory-design.md`

## Global Constraints

- Windows-first and CPU-first; no local GPU requirement.
- YouTube Shorts only; output 9:16 and exact requested duration from 1–180 seconds.
- No spoken dialogue; use natural vocal expressions, environmental ASMR, synchronized SFX and soft music.
- User references are primary style authority; generated work remains original and does not copy protected content shot-for-shot.
- Reference input supports public YouTube/Shorts URLs and uploaded video files.
- User references receive full accessible-video decode and deep multi-frame/audio analysis.
- Fresh topic research runs for every new Short; historical research is retained indefinitely and freshness-weighted.
- Gemini is primary intelligence provider; Hugging Face is primary image provider; configured fallbacks are capability/health based.
- Paid providers require explicit user permission and must never be selected automatically otherwise.
- API secrets are encrypted, masked, never logged, and protected from Git.
- PostgreSQL is automatically detected/provisioned when missing and supports migrations, backups and restore.
- Offline mode must not crash; local-capable stages remain usable and cloud stages report unavailable.
- Every object interaction must satisfy physical-action continuity constraints.
- Strict QC must fail critical violations and recover locally where possible.

---

## File Map

Create focused modules under `core/`, `providers/`, `tests/`, and `scripts/`; retain `app/` as UI/bootstrap compatibility. Existing prototype files are modified only after their current contents and tests are inspected.

- `app/main.py` — desktop bootstrap and UI wiring only.
- `app/setup.py` — first-run dependency/API/reference setup orchestration.
- `app/settings.py` — settings dialogs and provider/reference controls.
- `core/config.py` — validated application configuration.
- `core/security/vault.py` — encrypted secret vault.
- `core/db/models.py` — SQLAlchemy models.
- `core/db/session.py` — PostgreSQL connection/session lifecycle.
- `core/db/migrations.py` — schema migration runner.
- `core/db/backup.py` — backup/restore/integrity checks.
- `core/dependencies/postgres.py` — PostgreSQL detection/install/configure/health check.
- `core/providers/registry.py` — provider/key registry.
- `core/providers/router.py` — capability/health/cost-aware routing.
- `core/providers/health.py` — live checks, error classification and quota state.
- `providers/gemini/provider.py` — Gemini adapter.
- `providers/huggingface/provider.py` — HF image adapter.
- `providers/tavily/provider.py` — Tavily research adapter.
- `providers/custom/provider.py` — validated custom capability adapter.
- `core/reference/ingest.py` — URL/file ingestion.
- `core/reference/decode.py` — ffprobe/FFmpeg bounded full-timeline decode.
- `core/reference/analyze.py` — multi-frame/audio deep analysis.
- `core/reference/profile.py` — immutable reference profile model/versioning.
- `core/reference/synthesis.py` — cross-reference Master Style DNA.
- `core/research/discovery.py` — fresh web/video discovery.
- `core/research/knowledge.py` — persistent research KB/dedup/freshness.
- `core/character/profile.py` — master character profile.
- `core/character/reference_sheet.py` — reference-sheet generation/storage.
- `core/chat/controller.py` — persistent chatbox command interpretation.
- `core/story/planner.py` — duration-aware story planning.
- `core/story/timeline.py` — scene/beat/audio timeline contract.
- `core/continuity/state.py` — character/object/environment state ledger.
- `core/continuity/validator.py` — continuity and physical-action checks.
- `core/image/engine.py` — prompt/image orchestration.
- `core/animation/engine.py` — deterministic CPU-first image animation.
- `core/audio/library.py` — verified local audio catalog/license metadata.
- `core/audio/engine.py` — expressions/ASMR/SFX/music assembly.
- `core/audio/sync.py` — deterministic timing, ducking and mix automation.
- `core/qc/scene.py` — scene-level QC.
- `core/qc/final.py` — final MP4 QC.
- `core/recovery/engine.py` — checkpoint/retry/targeted recovery.
- `core/render/ffmpeg.py` — final render/export.
- `core/orchestrator/pipeline.py` — end-to-end state machine.
- `scripts/bootstrap_windows.ps1` — dependency bootstrap helper.
- `scripts/diagnose.py` — local diagnostics.
- `.github/workflows/ci.yml` — lint/type/unit/integration checks.
- `tests/` — unit, contract, integration and smoke tests.

---

### Task 1: Establish Test Harness and Configuration Contracts

**Files:**
- Create: `tests/conftest.py`, `tests/unit/test_config.py`
- Create: `core/config.py`
- Modify: `requirements.txt`

**Interfaces:**
- Produces validated `AppConfig`, paths, duration validation, offline/provider policy values.

- [ ] Write failing configuration tests.
- [ ] Run `pytest tests/unit/test_config.py -v` and verify expected failures.
- [ ] Implement configuration with safe defaults and environment overrides.
- [ ] Run focused tests and then the full test suite.
- [ ] Commit.

### Task 2: Secure Secret Vault

**Files:**
- Create: `core/security/vault.py`
- Create: `tests/unit/test_vault.py`
- Modify: `.gitignore`

**Interfaces:**
- `SecretVault.set(provider, key_id, secret)`
- `SecretVault.get(provider, key_id)`
- `SecretVault.delete(provider, key_id)`
- `SecretVault.list_metadata()`

- [ ] Write failing tests for encryption round-trip, masking metadata and missing secrets.
- [ ] Verify RED.
- [ ] Implement encrypted-at-rest vault and atomic writes.
- [ ] Verify GREEN.
- [ ] Commit.

### Task 3: PostgreSQL Provisioning and Database Layer

**Files:**
- Create: `core/dependencies/postgres.py`
- Create: `core/db/session.py`, `core/db/models.py`, `core/db/migrations.py`
- Create: `tests/unit/test_postgres_detection.py`, `tests/unit/test_db_models.py`

**Interfaces:**
- `PostgresManager.detect()`
- `PostgresManager.ensure_installed()`
- `PostgresManager.ensure_database()`
- `PostgresManager.health_check()`
- `Database.startup()` / `Database.shutdown()`

- [ ] Write failing detection and schema tests.
- [ ] Verify RED.
- [ ] Implement safe detection first; installer uses validated official distribution and never silently replaces an existing installation.
- [ ] Implement local DB/user creation and migrations.
- [ ] Verify with a disposable PostgreSQL integration environment where available.
- [ ] Commit.

### Task 4: Backup, Restore, Checkpoints and Recovery State

**Files:**
- Create: `core/db/backup.py`, `core/recovery/checkpoints.py`
- Create: `tests/unit/test_backup.py`, `tests/unit/test_checkpoints.py`

**Interfaces:**
- `BackupManager.create()`
- `BackupManager.verify()`
- `BackupManager.restore()`
- `CheckpointStore.save()` / `CheckpointStore.load()`

- [ ] Write failing tests.
- [ ] Verify RED.
- [ ] Implement atomic backup/checkpoint metadata and integrity checks.
- [ ] Verify GREEN.
- [ ] Commit.

### Task 5: Provider Registry, Multiple Keys, Health and Routing

**Files:**
- Create: `core/providers/registry.py`, `core/providers/health.py`, `core/providers/router.py`
- Create: `providers/gemini/provider.py`, `providers/huggingface/provider.py`, `providers/tavily/provider.py`, `providers/custom/provider.py`
- Create: `tests/unit/test_provider_router.py`, `tests/unit/test_provider_health.py`

**Interfaces:**
- `ProviderRegistry.add_key()`
- `ProviderRegistry.disable_key()`
- `ProviderHealth.check()`
- `ProviderRouter.select(capability, allow_paid=False)`

- [ ] Write failing routing tests for primary/fallback, multiple-key rotation, paid gate and offline behavior.
- [ ] Verify RED.
- [ ] Implement capability-based routing and error classification.
- [ ] Implement live provider adapters with secret-safe errors.
- [ ] Verify GREEN using mocked provider contracts plus optional live diagnostics.
- [ ] Commit.

### Task 6: First-Run Setup and API UI

**Files:**
- Create: `app/setup.py`, `app/settings.py`
- Modify: `app/main.py`
- Create: `tests/integration/test_setup_flow.py`

**Interfaces:**
- First-run setup requires one working Gemini, HF and Tavily credential.
- Successful live test registers the credential.
- Later settings support additional keys/providers.

- [ ] Write failing setup-state tests.
- [ ] Verify RED.
- [ ] Implement setup state machine and masked credential UI.
- [ ] Verify GREEN.
- [ ] Commit.

### Task 7: Reference Ingestion and Full Video Decode

**Files:**
- Create: `core/reference/ingest.py`, `core/reference/decode.py`
- Create: `tests/unit/test_reference_decode.py`, `tests/integration/test_reference_ingest.py`

**Interfaces:**
- `ReferenceIngestor.ingest_url()`
- `ReferenceIngestor.ingest_file()`
- `VideoDecoder.probe()`
- `VideoDecoder.iter_analysis_windows()`

- [ ] Write failing tests for URL/file validation, restricted input handling, metadata and bounded extraction.
- [ ] Verify RED.
- [ ] Implement FFmpeg/ffprobe processing without loading full media into RAM.
- [ ] Verify GREEN with synthetic fixtures.
- [ ] Commit.

### Task 8: Deep Reference Analyzer and Reference Profiles

**Files:**
- Create: `core/reference/analyze.py`, `core/reference/profile.py`
- Modify: existing `app/reference.py` to delegate to core.
- Create: `tests/unit/test_reference_analyzer.py`, `tests/unit/test_reference_profile.py`

**Interfaces:**
- `ReferenceAnalyzer.analyze(decoded_reference)`
- `ReferenceProfileRepository.save_version()`
- `ReferenceProfileRepository.list()`

- [ ] Write failing multi-segment visual/audio/timeline tests.
- [ ] Verify RED.
- [ ] Implement structured observations with timestamps, confidence and provenance.
- [ ] Verify GREEN.
- [ ] Commit.

### Task 9: Cross-Reference Master Style DNA

**Files:**
- Create: `core/reference/synthesis.py`
- Create: `tests/unit/test_style_synthesis.py`

**Interfaces:**
- `StyleSynthesizer.build_master(profiles)`
- `StyleSynthesizer.build_project_style(master, request, research)`

- [ ] Write failing tests for recurring patterns, contradictions, outliers and provenance.
- [ ] Verify RED.
- [ ] Implement weighted synthesis and versioning.
- [ ] Verify GREEN.
- [ ] Commit.

### Task 10: Automatic Fresh Content Research + Persistent Knowledge Base

**Files:**
- Create: `core/research/discovery.py`, `core/research/knowledge.py`
- Create: `tests/unit/test_research_kb.py`, `tests/integration/test_research_discovery.py`

**Interfaces:**
- `ResearchDiscovery.search(topic)`
- `ResearchKnowledge.upsert(items)`
- `ResearchKnowledge.retrieve(topic, limit)`
- `ResearchKnowledge.score_freshness(item)`

- [ ] Write failing deduplication/freshness/history tests.
- [ ] Verify RED.
- [ ] Implement Tavily + public-video discovery adapters and persistent merge logic.
- [ ] Verify GREEN with mocked sources.
- [ ] Commit.

### Task 11: Character Profile and Reference Sheet

**Files:**
- Create: `core/character/profile.py`, `core/character/reference_sheet.py`
- Create: `tests/unit/test_character_profile.py`

**Interfaces:**
- `CharacterProfile.create()`
- `CharacterProfile.apply_instruction()`
- `ReferenceSheet.build()`

- [ ] Write failing consistency/update tests.
- [ ] Verify RED.
- [ ] Implement profile/state schema and reference-sheet artifact contract.
- [ ] Verify GREEN.
- [ ] Commit.

### Task 12: Persistent Chat Control Plane

**Files:**
- Create: `core/chat/controller.py`
- Create: `tests/unit/test_chat_controller.py`

**Interfaces:**
- `ChatController.apply(message, project_context)`
- Must update project/style/character settings without re-requesting references.

- [ ] Write failing natural-language command contract tests.
- [ ] Verify RED.
- [ ] Implement structured change extraction using available intelligence provider with deterministic validation.
- [ ] Verify GREEN.
- [ ] Commit.

### Task 13: Story, Scene, Timeline and Continuity Contracts

**Files:**
- Create: `core/story/planner.py`, `core/story/timeline.py`
- Create: `core/continuity/state.py`, `core/continuity/validator.py`
- Create: `tests/unit/test_timeline.py`, `tests/unit/test_continuity.py`

**Interfaces:**
- `StoryPlanner.plan(request, duration, style, character, research)`
- `TimelineBuilder.build(story)`
- `ContinuityLedger.apply(action)`
- `ContinuityValidator.validate(scene_a, scene_b)`

- [ ] Write failing duration/beat/physical-action tests.
- [ ] Verify RED.
- [ ] Implement deterministic timeline schema with multiple meaningful visual beats per animation segment and explicit object state transitions.
- [ ] Verify GREEN.
- [ ] Commit.

### Task 14: Image Generation Engine

**Files:**
- Create: `core/image/engine.py`
- Create: `tests/unit/test_image_engine.py`

**Interfaces:**
- `ImageEngine.generate(scene_contract, router)`

- [ ] Write failing prompt/character/reference/paid-gate tests.
- [ ] Verify RED.
- [ ] Implement image generation with HF-first routing and fallback.
- [ ] Verify GREEN using provider mocks.
- [ ] Commit.

### Task 15: CPU-First Local Animation

**Files:**
- Create: `core/animation/engine.py`
- Create: `tests/unit/test_animation_engine.py`

**Interfaces:**
- `AnimationEngine.render(scene_image, motion_plan, output_path)`

- [ ] Write failing tests for deterministic duration, aspect ratio, multiple beats and resource bounds.
- [ ] Verify RED.
- [ ] Implement lightweight pan/zoom/parallax/particle/mask transforms and FFmpeg-compatible intermediate rendering.
- [ ] Verify GREEN with synthetic images.
- [ ] Commit.

### Task 16: Audio Library, ASMR/SFX/Expressions and Licensed Music

**Files:**
- Create: `core/audio/library.py`, `core/audio/engine.py`, `core/audio/sync.py`
- Create: `tests/unit/test_audio_engine.py`, `tests/unit/test_audio_sync.py`

**Interfaces:**
- `AudioLibrary.find_verified(criteria)`
- `AudioEngine.build(timeline)`
- `AudioSync.mix(events, duration)`

- [ ] Write failing tests for no-dialogue enforcement, license verification, timestamp alignment, ducking and clipping detection.
- [ ] Verify RED.
- [ ] Implement local audio catalog and deterministic mix automation.
- [ ] Verify GREEN.
- [ ] Commit.

### Task 17: Strict Scene and Final QC

**Files:**
- Create: `core/qc/scene.py`, `core/qc/final.py`
- Create: `tests/unit/test_scene_qc.py`, `tests/unit/test_final_qc.py`

**Interfaces:**
- `SceneQC.check(scene)`
- `FinalQC.check(video, expected_duration)`

- [ ] Write failing tests for every critical acceptance gate.
- [ ] Verify RED.
- [ ] Implement fail-closed critical checks and machine-readable findings.
- [ ] Verify GREEN.
- [ ] Commit.

### Task 18: Targeted Recovery and End-to-End Orchestrator

**Files:**
- Create: `core/recovery/engine.py`, `core/orchestrator/pipeline.py`
- Modify: `app/pipeline.py` to delegate to orchestrator.
- Create: `tests/integration/test_pipeline.py`

**Interfaces:**
- `RecoveryEngine.recover(failure, checkpoint)`
- `ShortsOrchestrator.generate(request)`

- [ ] Write failing integration tests for resume, targeted regeneration and offline cloud failure handling.
- [ ] Verify RED.
- [ ] Implement checkpointed state machine from request through final MP4.
- [ ] Verify GREEN with fully mocked providers and synthetic assets.
- [ ] Commit.

### Task 19: FFmpeg Final Renderer and Windows Diagnostics

**Files:**
- Create: `core/render/ffmpeg.py`, `scripts/diagnose.py`, `scripts/bootstrap_windows.ps1`
- Modify: `setup.bat`, `run.bat`
- Create: `tests/integration/test_render.py`

**Interfaces:**
- `FFmpegRenderer.render(timeline, output_path)`
- `Diagnostics.run()`

- [ ] Write failing render/diagnostic tests.
- [ ] Verify RED.
- [ ] Implement deterministic 9:16 H.264/AAC rendering, exact duration and validation.
- [ ] Verify GREEN with FFmpeg fixture.
- [ ] Commit.

### Task 20: UI Integration, Offline State and Reference Re-analysis

**Files:**
- Modify: `app/main.py`, `app/reference.py`
- Modify/create: `app/settings.py`
- Create: `tests/integration/test_ui_state.py`

- [ ] Write failing UI state tests for first run, later run, offline mode, API manager and re-analysis.
- [ ] Verify RED.
- [ ] Wire UI to the completed core contracts; keep UI free of provider/database business logic.
- [ ] Verify GREEN.
- [ ] Commit.

### Task 21: CI, Security Checks and Documentation

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `README.md`, `requirements.txt`, `.gitignore`
- Create: `INSTALL_WINDOWS.md`, `.env.example`, `config.example.yaml`

- [ ] Add unit/integration test jobs, syntax checks and secret-pattern checks.
- [ ] Run CI-equivalent commands locally.
- [ ] Document first-run setup, PostgreSQL provisioning, FFmpeg requirement, offline behavior, backups and provider permissions.
- [ ] Verify clean install instructions.
- [ ] Commit.

### Task 22: Full Verification and Release Build

**Files:**
- Modify only files required by verification findings.
- Create: release/build helper files only if required.

- [ ] Run the complete test suite.
- [ ] Run diagnostics on Windows.
- [ ] Verify no secret files are tracked.
- [ ] Verify clean setup on a fresh environment.
- [ ] Generate a synthetic end-to-end Short with mocked/cloud-test providers as appropriate.
- [ ] Validate exact duration, 9:16, audio integrity, QC report and recovery checkpoint.
- [ ] Review Git diff and commit history.
- [ ] Produce release notes and a directly usable ZIP/release artifact when the runtime environment permits artifact creation.
