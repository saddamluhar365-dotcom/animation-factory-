from __future__ import annotations
from dataclasses import dataclass


@dataclass(order=True)
class AudioEvent:
    start: float
    end: float
    kind: str
    name: str
    volume: float = 0.35
    duck_music: bool = False

    def __post_init__(self):
        if not 0 <= self.volume <= 1:
            raise ValueError("Audio event volume must be between 0 and 1")


class AudioTimeline:
    def __init__(self, duration: float):
        if duration <= 0:
            raise ValueError("Audio timeline duration must be positive")
        self.duration = float(duration)
        self.events: list[AudioEvent] = []

    def add(self, event: AudioEvent) -> AudioEvent:
        self.events.append(event)
        self.events.sort(key=lambda e: (e.start, e.end, e.kind))
        return event

    def validate(self) -> list[str]:
        return validate_events(self.events, self.duration)

    def to_dict(self) -> dict:
        return {"duration": self.duration, "events": [e.__dict__ for e in self.events]}


def validate_events(events: list[AudioEvent], duration: float) -> list[str]:
    errors = []
    if duration <= 0:
        errors.append("duration must be positive")
        return errors
    for event in events:
        if event.start < 0 or event.end <= event.start or event.end > duration + 0.001:
            errors.append(f"invalid audio event: {event.name}")
    music = [e for e in events if e.kind == "music"]
    music.sort(key=lambda e: (e.start, e.end))
    for a, b in zip(music, music[1:]):
        if b.start < a.end:
            errors.append("overlapping music events")
    return errors
