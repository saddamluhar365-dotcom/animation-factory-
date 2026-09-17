from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from core.contracts import ProjectPlan, ScenePlan
from app.storage import get_keys, get_keys_metadata
from .contracts import VideoGenerationRequest, VideoProviderType
from .router import FalVideoRouter

logger = logging.getLogger(__name__)


class BaseVideoProvider(ABC):
    """Abstract plugin base for video clip generation."""

    @abstractmethod
    def generate_scene_clips(
        self,
        plan: ProjectPlan,
        project_dir: Path,
        status_cb=lambda s: None,
        allow_placeholders: bool = False,
    ) -> list[Path]:
        pass


class ImageAnimationVideoProvider(BaseVideoProvider):
    """Option 1: Image -> 60 FPS Animation using Hugging Face image generation and FFmpeg."""

    def generate_scene_clips(
        self,
        plan: ProjectPlan,
        project_dir: Path,
        status_cb=lambda s: None,
        allow_placeholders: bool = False,
    ) -> list[Path]:
        from app.pipeline import generate_images, animate_images
        expected_images = [project_dir / "images" / f"scene_{s.index:03d}.jpg" for s in plan.scenes]
        if all(p.is_file() and p.stat().st_size > 0 for p in expected_images):
            status_cb("Resuming with existing scene images...")
            images = expected_images
        else:
            status_cb("Generating scene images via Image -> Animation pipeline...")
            images = generate_images(
                plan=plan,
                project_dir=project_dir,
                status_cb=status_cb,
                allow_placeholders=allow_placeholders,
            )
        status_cb("Animating images into 60 FPS cinematic camera clips...")
        clips = animate_images(images=images, plan=plan, project_dir=project_dir)
        return clips


class FalVideoProvider(BaseVideoProvider):
    """Option 2: Direct video generation using healthy FAL API key pool and dynamic models."""

    def __init__(self, router: FalVideoRouter | None = None):
        if router is not None:
            self.router = router
        else:
            keys_meta = get_keys_metadata("fal")
            self.router = FalVideoRouter(api_keys=keys_meta)

    def generate_scene_clips(
        self,
        plan: ProjectPlan,
        project_dir: Path,
        status_cb=lambda s: None,
        allow_placeholders: bool = False,
    ) -> list[Path]:
        clips_dir = project_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)
        result = []

        total_scenes = len(plan.scenes)
        for scene in plan.scenes:
            clip_path = clips_dir / f"scene_{scene.index:03d}.mp4"
            scene_duration = max(1.0, scene.end - scene.start)
            first_action = scene.beats[0].action if scene.beats else ""
            
            # Format high-retention video prompt
            prompt_parts = [
                scene.visual_prompt,
                "vertical 9:16, 60 fps, cinematic macro motion, hyper-detailed, smooth continuous physical action, photorealistic",
            ]
            full_prompt = ", ".join(prompt_parts)

            status_cb(f"Scene {scene.index}/{total_scenes}: generating video via FAL Video...")
            req = VideoGenerationRequest(
                prompt=full_prompt,
                duration=scene_duration,
                scene_index=scene.index,
                total_scenes=total_scenes,
                aspect_ratio="9:16",
                action_text=first_action,
            )

            res = self.router.generate(
                request=req,
                output_path=clip_path,
                allow_placeholders=allow_placeholders,
            )
            status_cb(f"Scene {scene.index}: generated via {res.model_used} ({res.key_alias})")
            result.append(clip_path)

        return result


def resolve_video_provider(provider_name: str, **kwargs) -> BaseVideoProvider:
    """Factory to resolve configured video provider."""
    clean = (provider_name or "").lower().strip()
    if clean in ("fal", "fal_video", "fal video", VideoProviderType.FAL_VIDEO):
        return FalVideoProvider(**kwargs)
    return ImageAnimationVideoProvider()
