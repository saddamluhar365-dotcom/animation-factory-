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
        if self.start < 0 or self.end <= self.start:
            raise ValueError("Audio event timestamps must be increasing")
        if not 0 <= self.volume <= 1:
            raise ValueError("Audio event volume must be between 0 and 1")


class AudioTimeline:
    def __init__(self, duration: float):
        self.duration = float(duration)
        self.events: list[AudioEvent] = []

    def add(self, event: AudioEvent) -> AudioEvent:
        self.events.append(event)
        self.events.sort(key=lambda e: (e.start, e.end, e.kind))
        return event

    def validate(self) -> list[str]:
        errors = []
        for event in self.events:
            if event.end > self.duration + 0.001:
                errors.append(f"audio event {event.name} exceeds duration")
        for a, b in zip(self.events, self.events[1:]):
            if a.kind == "music" and b.kind == "music" and b.start < a.end:
                errors.append("overlapping music events")
        return errors

    def to_dict(self) -> dict:
        return {"duration": self.duration, "events": [e.__dict__ for e in self.events]}
