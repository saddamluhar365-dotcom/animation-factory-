from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class NoveltyStatus(str, Enum):
    NOVEL = "NOVEL"
    LOW_SIMILARITY = "LOW_SIMILARITY"
    NEAR_DUPLICATE = "NEAR_DUPLICATE"
    DUPLICATE = "DUPLICATE"


@dataclass
class ChannelProfile:
    id: int | None = None
    handle: str = ""
    channel_id: str = ""
    uploads_playlist_id: str = ""
    title: str = ""
    description: str = ""
    custom_url: str = ""
    subscriber_count: int = 0
    video_count: int = 0
    auto_sync_enabled: bool = True
    auto_analyze_enabled: bool = True
    auto_reference_enabled: bool = True
    prevent_recipe_repeats: bool = True
    last_synced_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChannelProfile:
        return cls(
            id=data.get("id"),
            handle=data.get("handle", ""),
            channel_id=data.get("channel_id", ""),
            uploads_playlist_id=data.get("uploads_playlist_id", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            custom_url=data.get("custom_url", ""),
            subscriber_count=int(data.get("subscriber_count", 0)),
            video_count=int(data.get("video_count", 0)),
            auto_sync_enabled=bool(data.get("auto_sync_enabled", True)),
            auto_analyze_enabled=bool(data.get("auto_analyze_enabled", True)),
            auto_reference_enabled=bool(data.get("auto_reference_enabled", True)),
            prevent_recipe_repeats=bool(data.get("prevent_recipe_repeats", True)),
            last_synced_at=data.get("last_synced_at"),
            metadata=data.get("metadata") or {},
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class ChannelVideo:
    id: int | None = None
    channel_profile_id: int | None = None
    youtube_video_id: str = ""
    title: str = ""
    description: str = ""
    published_at: str | None = None
    duration_seconds: int = 0
    is_short: bool = True
    video_url: str = ""
    thumbnail_url: str = ""
    etag: str = ""
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RecipeRecord:
    id: int | None = None
    channel_profile_id: int | None = None
    channel_video_id: int | None = None
    recipe_name: str = ""
    normalized_recipe_name: str = ""
    dish_category: str = ""
    cuisine: str = ""
    region: str = ""
    primary_ingredient: str = ""
    secondary_ingredients: list[str] = field(default_factory=list)
    cooking_method: str = ""
    flavor_profile: str = ""
    environment: str = ""
    signatures: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VideoDeepAnalysis:
    youtube_video_id: str = ""
    title: str = ""
    resolution: list[int] = field(default_factory=lambda: [1080, 1920])
    fps: float = 60.0
    duration_seconds: float = 0.0
    aspect_ratio: str = "9:16"
    scene_structure: dict[str, Any] = field(default_factory=dict)
    pacing: dict[str, Any] = field(default_factory=dict)
    visual_style: dict[str, Any] = field(default_factory=dict)
    consistency_anchors: list[str] = field(default_factory=list)
    camera_movement: dict[str, Any] = field(default_factory=dict)
    animation_motion_quality: dict[str, Any] = field(default_factory=dict)
    story_structure: dict[str, Any] = field(default_factory=dict)
    recipe_content_patterns: dict[str, Any] = field(default_factory=dict)
    asmr_audio_profile: dict[str, Any] = field(default_factory=dict)
    sfx_music_patterns: dict[str, Any] = field(default_factory=dict)
    transitions: dict[str, Any] = field(default_factory=dict)
    successful_characteristics: list[str] = field(default_factory=list)
    weak_patterns_identified: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ChannelDNA:
    channel_profile_id: int | None = None
    dna_profile: dict[str, Any] = field(default_factory=dict)
    saturation_metrics: dict[str, Any] = field(default_factory=dict)
    version: int = 1
    updated_at: str | None = None

    @property
    def winning_style_dna(self) -> dict[str, Any]:
        return self.dna_profile.get("winning_style_dna") or {}

    @property
    def content_recipe_dna(self) -> dict[str, Any]:
        return self.dna_profile.get("content_recipe_dna") or {}

    @property
    def visual_dna(self) -> dict[str, Any]:
        return self.dna_profile.get("visual_dna") or {}

    @property
    def animation_dna(self) -> dict[str, Any]:
        return self.dna_profile.get("animation_dna") or {}

    @property
    def audio_asmr_dna(self) -> dict[str, Any]:
        return self.dna_profile.get("audio_asmr_dna") or {}

    @property
    def pacing_dna(self) -> dict[str, Any]:
        return self.dna_profile.get("pacing_dna") or {}

    @property
    def story_dna(self) -> dict[str, Any]:
        return self.dna_profile.get("story_dna") or {}

    @property
    def quality_rules(self) -> list[str]:
        return self.dna_profile.get("quality_rules") or []

    @property
    def avoid_bad_patterns(self) -> list[str]:
        return self.dna_profile.get("avoid_bad_patterns") or []

    @property
    def previously_used_recipes(self) -> list[str]:
        return self.dna_profile.get("previously_used_recipes") or []

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ImprovementRecord:
    id: int | None = None
    channel_profile_id: int | None = None
    area: str = "general"
    observation: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    recommendation: str = ""
    confidence: float = 1.0
    status: str = "active"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NoveltyVerdict:
    status: NoveltyStatus
    score: float  # 0.0 to 1.0 (1.0 = completely novel, 0.0 = exact duplicate)
    reasons: list[str] = field(default_factory=list)
    matched_recipe: str | None = None
    matched_video_id: str | None = None

    @property
    def is_acceptable(self) -> bool:
        return self.status in (NoveltyStatus.NOVEL, NoveltyStatus.LOW_SIMILARITY)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "score": self.score,
            "acceptable": self.is_acceptable,
            "reasons": self.reasons,
            "matched_recipe": self.matched_recipe,
            "matched_video_id": self.matched_video_id,
        }


@dataclass
class SyncResult:
    status: str = "success"
    videos_discovered: int = 0
    videos_added: int = 0
    shorts_added: int = 0
    errors: list[str] = field(default_factory=list)
