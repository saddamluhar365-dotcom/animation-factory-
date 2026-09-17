from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone


def build_master_style(profiles: list[dict]) -> dict:
    if not profiles:
        return {"schema_version": 1, "characteristics": {}, "provenance": [], "generated_at": datetime.now(timezone.utc).isoformat()}
    technical = [p.get("technical", {}) for p in profiles]
    ratios = [f"{x.get('width')}x{x.get('height')}" for x in technical if x.get("width") and x.get("height")]
    return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "provenance": [p.get("source_hash") for p in profiles], "reference_count": len(profiles), "characteristics": {"aspect_ratios": Counter(ratios).most_common(), "analysis_frame_counts": [p.get("visual_features", {}).get("frame_count", 0) for p in profiles], "audio_coverage": sum(bool(p.get("audio_extracted")) for p in profiles) / len(profiles)}}
