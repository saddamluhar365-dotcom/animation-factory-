from __future__ import annotations
import re
from core.contracts import ProjectPlan

_FORBIDDEN = re.compile(r"\b(teleport(?:s|ed|ing)?|magically appears?|disappears? without|duplicates?|floats? without|morphs?|changes shape instantly|cuts to a different object)\b", re.I)


def validate_state_transition(previous: dict, current: dict) -> list[str]:
    errors = []
    before = previous.get("objects", {})
    after = current.get("objects", {})
    for name in before:
        if name not in after:
            errors.append(f"object disappeared: {name}")
        elif isinstance(before[name], dict) and isinstance(after[name], dict):
            for key in ("size", "shape", "identity"):
                if key in before[name] and key in after[name] and before[name][key] != after[name][key]:
                    errors.append(f"object changed {key}: {name}")
    return errors


def validate_plan_continuity(plan: ProjectPlan) -> list[str]:
    errors = []
    if not plan.scenes:
        return ["plan has no scenes"]
    cursor = 0.0
    for scene in plan.scenes:
        if abs(scene.start - cursor) > 0.01:
            errors.append(f"scene {scene.index}: gap/overlap at {scene.start:.3f}s")
        if scene.end <= scene.start:
            errors.append(f"scene {scene.index}: invalid time range")
        if not 3 <= len(scene.beats) <= 5:
            errors.append(f"scene {scene.index}: must have 3-5 beats")
        previous = scene.start
        for beat in scene.beats:
            if beat.start < scene.start - 0.01 or beat.end > scene.end + 0.01 or beat.start < previous - 0.01:
                errors.append(f"scene {scene.index}: beat timing is outside scene")
            if _FORBIDDEN.search(beat.action + " " + scene.visual_prompt):
                errors.append(f"scene {scene.index}: non-physical object transition detected")
            previous = beat.end
        cursor = scene.end
    if abs(cursor - plan.duration) > 0.01:
        errors.append(f"plan total {cursor:.3f}s does not equal requested {plan.duration}s")
    return errors
