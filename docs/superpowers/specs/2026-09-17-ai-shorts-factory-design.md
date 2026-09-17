# AI Shorts Factory — System Design

**Date:** 2026-09-17
**Status:** Approved for implementation planning

## Goal
Build a Windows-first, CPU-first YouTube Shorts factory that turns a user request plus persistent reference/style intelligence and fresh content research into an original, silent, ASMR-rich 1–180 second vertical Short, with local animation/rendering, strict QC, recovery, and persistent PostgreSQL intelligence.

## Locked decisions

1. Reference input supports both YouTube/Shorts URLs and uploaded video files.
2. User-provided references receive full accessible-video decode and deep analysis, not single-frame analysis.
3. Reference analysis covers technical properties, shots/scenes, multi-frame visual analysis, character/environment continuity, camera, animation, lighting/color, pacing, story structure, emotional progression, editing/transitions, audio, ASMR, SFX, music, and synchronization.
4. User references are the primary style authority. Generated work follows their high-level production DNA while remaining original and avoiding shot-for-shot/protected-content copying.
5. The system automatically researches current content related to each new topic using Tavily plus YouTube/public-web discovery.
6. Research is persistent. Fresh research is merged with historical research using deduplication, validation, relevance, and freshness weighting; old data is retained indefinitely unless the user cleans it up.
7. Reference profiles, Master Style DNA, Character Profiles, and Research Knowledge are separate data domains.
8. Multiple reference profiles are retained and cross-analyzed into Master Style DNA. Project-specific style plans adapt that DNA to each request.
9. Character consistency is maintained through an automatically generated Master Character Profile and Character Reference Sheet. User chat instructions can intentionally update it.
10. Gemini is the primary story/intelligence provider, with configured alternate LLM providers and a local rules/logic fallback.
11. Hugging Face is the primary image provider, with configured alternate image providers as automatic fallback.
12. Paid providers never execute automatically without explicit user permission.
13. Provider routing is capability/health/quota/rate-limit based and supports multiple keys per provider plus fallback/rotation.
14. API secrets use encrypted local storage, masked UI, secret-safe logging, and repository secret protection.
15. First launch requires one working Gemini key, one Hugging Face token, and one Tavily key. Later Settings → APIs supports additional providers/keys.
16. Heavy AI work remains cloud/API-based; animation, audio assembly, synchronization, QC, and FFmpeg rendering remain local and CPU-first.
17. Output is YouTube Shorts only for this project scope, 9:16, exact requested duration from 1–180 seconds.
18. Shorts contain no spoken dialogue. They use natural human vocal expressions, environmental ASMR, synchronized SFX, and soft music.
19. Music uses a local licensed/royalty-cleared library with source/license metadata and rejects unknown/unverified tracks by default.
20. Timeline synchronization is deterministic: visual beats, expressions, ambience, SFX, music, ducking, and transitions use explicit timestamps.
21. Physical-action realism is strict: object identity, size, presence, position, contact, and movement must remain physically logical and continuous; no teleporting, disappearing, duplicating, floating, morphing, or unexplained changes.
22. Strict automated QC checks character/object/scene continuity, physical actions, image and animation quality, audio/SFX sync, music levels, black frames, duplicate frames, 9:16, exact duration, clipping, and render integrity. Failed stages receive targeted regeneration/re-render where possible.
23. PostgreSQL is automatically provisioned on first run when missing, using an approved official distribution, without silently replacing an existing installation. The app creates its local database/user, applies migrations, and health-checks the instance.
24. PostgreSQL is local and offline-capable. Existing projects, saved intelligence, local assets, animation, audio, synchronization, rendering, and QC continue offline; cloud features are marked unavailable rather than crashing the application.
25. PostgreSQL has automatic backups, project checkpoints, crash recovery, migrations, restore support, backup integrity verification, and configurable retention.
26. User chat is the persistent control plane after setup. Instructions modify the current project/style/character settings without repeatedly asking for references.

## Architecture

```text
User Request + Duration
        │
        ├── User References ──> Full Decode ──> Reference Profiles ──┐
        │                                                             │
        └── Fresh Topic Research ──> Research KB <── Historical Data ─┤
                                                                      ↓
                                                            Master Style DNA
                                                                      │
                                                            Character Profile
                                                                      ↓
                                                             Project Planner
                                                                      ↓
                                                        Story + Scene Timeline
                                                                      ↓
                                                             Image Generation
                                                                      ↓
                                                      Local CPU Animation Engine
                                                                      ↓
                                             Expressions + ASMR + SFX + Music
                                                                      ↓
                                                            Sync/Mix Engine
                                                                      ↓
                                                               Strict QC
                                                                      ↓
                                                           Auto Recovery
                                                                      ↓
                                                               FFmpeg
                                                                      ↓
                                                            YouTube Short
```

## Reference Intelligence

### Ingestion
- Accept local video files and supported public YouTube/Shorts URLs.
- URLs are downloaded/processed only when publicly accessible and technically permitted.
- Restricted/private/unavailable URLs produce an actionable error and expose upload fallback.
- Preserve source metadata, acquisition timestamp, hashes, and processing status.

### Full decode
Use FFmpeg/ffprobe and bounded frame/audio extraction to avoid loading full videos into RAM. Segment long references into analysis windows. Store derived artifacts and hashes in cache.

### Deep analysis
Produce structured observations with timestamps and confidence. Never rely on a single sampled frame. Visual and audio observations are separately represented and then synchronized.

### Profile synthesis
Each reference receives an immutable versioned profile. Multiple profiles are cross-analyzed for recurring patterns, contradictions, and outliers. Master Style DNA contains weighted characteristics and provenance back to source profiles.

## Content Intelligence

For every new topic, perform fresh Tavily/web and public-video discovery. Store research items with source, retrieval timestamp, topic tags, freshness, confidence, and evidence summary. Deduplicate against historical knowledge and retain old records with reduced freshness weight rather than deleting them automatically.

Research intelligence can inform topic selection, pacing, visual/audio conventions, and factual context, but it is not silently promoted to the user's primary Style DNA.

## Generation

Planner inputs:
- user prompt/chat changes
- duration 1–180 seconds
- Master Style DNA
- Character Profile
- relevant historical + fresh research
- continuity constraints
- available provider capabilities

Planner outputs a deterministic scene/timeline contract containing visual beats, image prompts, motion instructions, object states, character states, audio events, music placement, transitions, and QC expectations.

Images are generated by capability routing. Hugging Face is preferred; alternatives are used only when eligible and healthy. Paid providers require an explicit permission flag.

## Local animation

Use image-first animation designed for the user's Ryzen 3 3200G-class CPU/RAM environment. Prefer lightweight camera motion, parallax, zoom/pan, layered effects, particles, masks, and deterministic transforms over heavyweight local video generation. Every scene must have multiple meaningful visual beats rather than one static action.

## Audio

No dialogue. Build audio from local verified libraries:
- human vocal expressions
- environmental ambience
- action SFX
- licensed/cleared music

Every audio event has a timeline timestamp and source/license metadata. Mixer supports fades, gain automation, ducking, normalization, and clipping detection.

## Continuity and physical realism

Maintain an explicit state ledger for each scene: character appearance, clothing, object IDs, object transforms/locations, held objects, environment, time, lighting, and relevant action phases. Actions that involve objects require causal contact and state transitions. QC compares adjacent states and flags impossible transitions.

## QC and recovery

QC operates at scene and final-output levels. It should fail closed on critical violations. Recovery is targeted: regenerate only the affected prompt/image/animation/audio stage when the failure is local; re-plan only when the dependency graph makes local recovery invalid. Checkpoints allow resumption after crashes.

## Persistence

PostgreSQL stores durable structured intelligence and project state. Large media files remain in the filesystem/object-like local asset directories with hashes and metadata in PostgreSQL. Encrypted API secrets stay in the local secret vault rather than ordinary project tables.

## Security

- Encrypt secrets at rest.
- Never print keys/tokens in logs or exceptions.
- Mask credentials in UI.
- Prevent secret files from Git tracking.
- Validate provider endpoints and TLS for custom providers.
- Explicit permission gate for paid providers.

## Offline behavior

When offline, the system starts normally, loads PostgreSQL and local profiles, executes all local-capable pipeline stages, and marks cloud-dependent operations unavailable. Cached provider results may be reused when policy permits. The system never claims a fresh web/API result when it did not obtain one.

## Scope boundaries

- YouTube Shorts is the only publishing/export target in this implementation.
- No automatic copying of protected reference content.
- No silent paid-provider usage.
- No requirement for a local GPU.

## Acceptance criteria

A clean Windows machine can run setup, provision required local dependencies, configure minimum APIs, ingest references, build persistent intelligence, generate a 1–180 second original Short, locally animate and mix it, pass strict QC, render a valid 9:16 MP4, persist project/research/reference state in PostgreSQL, back up recoverable state, and resume after an interrupted generation.
