from __future__ import annotations


def validate_metadata(meta: dict, requested_duration: float, tolerance: float = 0.08) -> list[str]:
    errors = []
    duration = float(meta.get("duration", 0) or 0)
    width, height = int(meta.get("width", 0) or 0), int(meta.get("height", 0) or 0)
    if abs(duration - requested_duration) > tolerance:
        errors.append(f"duration mismatch: {duration:.3f}s vs {requested_duration:.3f}s")
    if width != 1080 or height != 1920:
        errors.append(f"resolution must be 1080x1920, got {width}x{height}")
    if not meta.get("video_codec"):
        errors.append("missing video stream")
    if not meta.get("has_audio"):
        errors.append("missing audio stream")
    return errors
