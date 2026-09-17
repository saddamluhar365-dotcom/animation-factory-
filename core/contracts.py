from __future__ import annotations
from dataclasses import asdict, dataclass, field


@dataclass
class SceneBeat:
    start: float
    end: float
    action: str
    camera: str = "subtle push-in"

    def __post_init__(self):
        if self.start < 0 or self.end <= self.start:
            raise ValueError("SceneBeat timestamps must be increasing")


@dataclass
class ScenePlan:
    index: int
    start: float
    end: float
    beats: list[SceneBeat]
    visual_prompt: str
    audio_events: list[dict] = field(default_factory=list)
    continuity: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.end <= self.start:
            raise ValueError("Scene timestamps must be increasing")
        if not self.beats:
            raise ValueError("Scene must contain at least one visual beat")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProjectPlan:
    duration: int
    title: str
    scenes: list[ScenePlan]
    style: dict = field(default_factory=dict)
    character: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
