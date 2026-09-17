from __future__ import annotations

MIN_DURATION = 1
MAX_DURATION = 180
SCENE_TARGET = 10


def validate_duration(value: int | float) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Duration must be an integer number of seconds") from exc
    if not MIN_DURATION <= value <= MAX_DURATION:
        raise ValueError(f"Duration must be between {MIN_DURATION} and {MAX_DURATION} seconds")
    return value


def scene_count(duration: int | float) -> int:
    duration = validate_duration(duration)
    return max(1, min(18, (duration + SCENE_TARGET - 1) // SCENE_TARGET))


def distribute_duration(duration: int | float, count: int | None = None) -> list[float]:
    duration = validate_duration(duration)
    count = count or scene_count(duration)
    if count < 1:
        raise ValueError("Scene count must be positive")
    base = duration / count
    values = [round(base, 3) for _ in range(count - 1)]
    values.append(round(duration - sum(values), 3))
    return values
