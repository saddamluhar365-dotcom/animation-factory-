from __future__ import annotations
from core.duration import scene_count, validate_duration
from core.contracts import ProjectPlan, SceneBeat, ScenePlan


def build_fallback_plan(instruction: str, duration: int, style: dict | None = None, character: dict | None = None) -> ProjectPlan:
    duration = validate_duration(duration)
    count = scene_count(duration)
    base = duration / count
    scenes = []
    cursor = 0.0
    for i in range(count):
        end = duration if i == count - 1 else round(cursor + base, 3)
        beats = []
        span = end - cursor
        beat_count = max(3, min(5, int(round(span / 2))))
        for b in range(beat_count):
            start = cursor + span * b / beat_count
            bend = cursor + span * (b + 1) / beat_count
            beats.append(SceneBeat(round(start, 3), round(bend, 3), f"Original visual beat for: {instruction}", "subtle camera movement"))
        scenes.append(ScenePlan(i + 1, round(cursor, 3), round(end, 3), beats, f"Original cinematic vertical scene for {instruction}; preserve character and object continuity; no text; no dialogue."))
        cursor = end
    return ProjectPlan(duration, instruction[:80], scenes, style or {}, character or {})
