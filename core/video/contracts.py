from __future__ import annotations
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path


class KeyHealthStatus(str, Enum):
    ACTIVE = "active"
    RATE_LIMITED = "rate_limited"
    INVALID = "invalid"
    DISABLED = "disabled"


class VideoProviderType(str, Enum):
    IMAGE_ANIMATION = "image_animation"
    FAL_VIDEO = "fal_video"


@dataclass
class VideoGenerationRequest:
    prompt: str
    duration: float
    scene_index: int = 1
    total_scenes: int = 1
    aspect_ratio: str = "9:16"
    width: int = 1080
    height: int = 1920
    fps: int = 60
    seed: int | None = None
    action_text: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VideoGenerationResult:
    video_path: Path
    provider: str
    model_used: str
    key_alias: str
    latency_seconds: float
    status: str
    details: dict

    def to_dict(self) -> dict:
        d = asdict(self)
        d["video_path"] = str(self.video_path)
        return d
