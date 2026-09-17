from __future__ import annotations


def validate_vertical(duration: float, width: int, height: int) -> list[str]:
    errors = []
    if width != 1080 or height != 1920:
        errors.append(f"resolution must be 1080x1920, got {width}x{height}")
    if duration <= 0:
        errors.append("duration must be positive")
    return errors


def validate_metadata(meta: dict, requested_duration: float, tolerance: float = 0.08) -> list[str]:
    errors = []
    duration = float(meta.get("duration", 0) or 0)
    width, height = int(meta.get("width", 0) or 0), int(meta.get("height", 0) or 0)
    errors.extend(validate_vertical(duration, width, height))
    if abs(duration - requested_duration) > tolerance:
        errors.append(f"duration mismatch: {duration:.3f}s vs {requested_duration:.3f}s")
    if not meta.get("video_codec"):
        errors.append("missing video stream")
    if not meta.get("has_audio"):
        errors.append("missing audio stream")
    fps = meta.get("fps")
    if fps is not None and fps < 12:
        errors.append(f"invalid framerate: {fps:.1f} fps")
    audio_dur = meta.get("audio_duration")
    video_dur = meta.get("video_duration")
    if audio_dur and video_dur and abs(audio_dur - video_dur) > tolerance + 0.2:
        errors.append(f"audio/video duration misalignment: audio {audio_dur:.2f}s vs video {video_dur:.2f}s")
    return errors
