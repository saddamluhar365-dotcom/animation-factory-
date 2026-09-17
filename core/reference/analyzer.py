from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
from .decode import extract_audio, extract_frames, probe
from .ingest import content_hash


class ReferenceAnalyzer:
    """Build a bounded, timestamp-aware reference profile without loading a whole video into RAM."""

    def analyze(self, source: Path, work_dir: Path) -> dict:
        meta = probe(source)
        frames = extract_frames(source, work_dir / "frames", count=min(48, max(12, math.ceil(meta["duration"] * 0.75))))
        audio = extract_audio(source, work_dir / "audio.wav")
        observations = []
        duration = max(meta["duration"], 0.1)
        for index, frame in enumerate(frames):
            observations.append({"timestamp": round((index + 0.5) * duration / len(frames), 3), "frame": frame.name})
        return {"schema_version": 1, "source_hash": content_hash(source), "technical": meta, "frames": observations, "audio_extracted": bool(audio), "visual_features": {"frame_count": len(frames)}, "audio_features": {"available": bool(audio)}, "analysis_notes": ["Multi-frame analysis completed; semantic visual/audio interpretation can be enriched by configured vision/LLM providers."]}

    def save(self, profile: dict, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
