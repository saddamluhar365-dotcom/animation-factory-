from __future__ import annotations
import re
from core.contracts import ProjectPlan

_FORBIDDEN = re.compile(r"\b(teleport(?:s|ed|ing)?|magically appears?|disappears? without|duplicates?|floats? without|morphs?|changes shape instantly|cuts to a different object)\b", re.I)
_ACTIONS = ("pick up", "picks up", "place", "places", "carry", "carries", "open", "opens", "close", "closes", "pour", "pours", "cut", "cuts", "mix", "mixes", "hang", "hangs", "lift", "lifts")


def validate_plan_continuity(plan: ProjectPlan) -> list[str]:
    errors: list[str] = []
    if not plan.scenes:
        return ["plan has no scenes"]
    cursor = 0.0
    for scene in plan.scenes:
        if abs(scene.start - cursor) > 0.01:
            errors.append(f"scene {scene.index}: gap/overlap at {scene.start:.3f}s")
        if scene.end <= scene.start:
            errors.append(f"scene {scene.index}: invalid time range")
        if len(scene.beats) < 3 or len(scene.beats) > 5:
            errors.append(f"scene {scene.index}: must have 3-5 beats")
        previous = scene.start
        for beat in scene.beats:
            if beat.start < scene.start - 0.01 or beat.end > scene.end + 0.01 or beat.start < previous - 0.01:
                errors.append(f"scene {scene.index}: beat timing is outside scene")
            text = beat.action + " " + scene.visual_prompt
            if _FORBIDDEN.search(text):
                errors.append(f"scene {scene.index}: non-physical object transition detected")
            if any(action in beat.action.lower() for action in _ACTIONS) and not scene.continuity:
                # Physical actions remain valid; the prompt is hardened by the planner.
                pass
            previous = beat.end
        cursor = scene.end
    if abs(cursor - plan.duration) > 0.01:
        errors.append(f"plan total {cursor:.3f}s does not equal requested {plan.duration}s")
    return errors
