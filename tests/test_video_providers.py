from __future__ import annotations
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from PIL import Image
import pytest
from core.contracts import ProjectPlan, SceneBeat, ScenePlan
from core.video.providers import (
    resolve_video_provider,
    ImageAnimationVideoProvider,
    FalVideoProvider,
)
from core.video.contracts import VideoGenerationResult
from app.pipeline import run_project


def test_resolve_video_provider():
    p1 = resolve_video_provider("image_animation")
    assert isinstance(p1, ImageAnimationVideoProvider)

    p2 = resolve_video_provider("fal_video")
    assert isinstance(p2, FalVideoProvider)

    p3 = resolve_video_provider("fal")
    assert isinstance(p3, FalVideoProvider)

    # Default fallback
    p_def = resolve_video_provider("unknown_provider")
    assert isinstance(p_def, ImageAnimationVideoProvider)


def test_e2e_pipeline_with_image_animation_mode(tmp_path: Path):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg not available")

    # Mock HF image generator
    with patch("app.pipeline.hf_text_to_image") as mock_hf:
        img_bytes = tmp_path / "fixture.jpg"
        Image.new("RGB", (1080, 1920), (120, 150, 90)).save(img_bytes)
        mock_hf.return_value = img_bytes.read_bytes()

        out = run_project(
            instruction="Simple breakfast prep",
            duration=3,
            project_dir=tmp_path / "proj_img",
            video_provider="image_animation",
            allow_placeholders=True,
        )
        assert out.exists()
        assert out.stat().st_size > 1000


def test_e2e_pipeline_with_fal_video_mode(tmp_path: Path):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg not available")

    # Mock FalVideoRouter.generate to produce valid test clips
    with patch("core.video.router.FalVideoRouter.generate") as mock_gen:
        def fake_generate(request, output_path, allow_placeholders=False):
            # Render a small 60 FPS clip as fixture
            from core.render.animation import animate_scene_image
            img_path = tmp_path / "tmp_frame.jpg"
            Image.new("RGB", (1080, 1920), (140, 110, 70)).save(img_path)
            animate_scene_image(img_path, output_path, duration=request.duration, fps=60)
            return VideoGenerationResult(
                video_path=output_path,
                provider="fal_video",
                model_used="fal-ai/kling-video/v1/standard/text-to-video",
                key_alias="fal_...test",
                latency_seconds=1.2,
                status="success",
                details={},
            )
        mock_gen.side_effect = fake_generate

        out = run_project(
            instruction="Sizzling garlic butter steak",
            duration=3,
            project_dir=tmp_path / "proj_fal",
            video_provider="fal_video",
            allow_placeholders=True,
        )
        assert out.exists()
        assert out.stat().st_size > 1000
        assert mock_gen.call_count >= 1
