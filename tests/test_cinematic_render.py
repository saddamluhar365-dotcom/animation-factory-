from __future__ import annotations
import shutil
from pathlib import Path
from PIL import Image
import pytest
from core.render.animation import (
    CameraMotionProfile,
    build_zoompan_filter,
    select_motion_profile,
    animate_scene_image,
)
from core.render.transitions import concat_with_transitions
from core.qc.engine import ffprobe_json


def test_motion_profile_selection():
    assert select_motion_profile(1, 4, "establish") == CameraMotionProfile.MACRO_PUSH_IN
    assert select_motion_profile(4, 4, "plate") == CameraMotionProfile.REVEAL_PULL_OUT
    assert select_motion_profile(2, 4, "chop onions") == CameraMotionProfile.DYNAMIC_TILT
    assert select_motion_profile(3, 4, "sear steak") == CameraMotionProfile.MACRO_PUSH_IN


def test_build_zoompan_filter():
    vf_push = build_zoompan_filter(CameraMotionProfile.MACRO_PUSH_IN, duration=2.5, fps=60)
    assert "fps=60" in vf_push
    assert "1080:1920" in vf_push
    assert "scale=" in vf_push
    assert "crop=" in vf_push

    vf_drift = build_zoompan_filter(CameraMotionProfile.CINEMATIC_DRIFT, duration=2.0, fps=60)
    assert "fps=60" in vf_drift

    vf_reveal = build_zoompan_filter(CameraMotionProfile.REVEAL_PULL_OUT, duration=3.0, fps=60)
    assert "max(1.0" in vf_reveal


def test_animate_scene_image_high_fps(tmp_path: Path):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg not available")

    # Create dummy 1080x1920 image
    img_path = tmp_path / "test_frame.jpg"
    img = Image.new("RGB", (1080, 1920), color=(180, 120, 70))
    img.save(img_path)

    out_clip = tmp_path / "clip.mp4"
    res = animate_scene_image(
        image=img_path,
        output=out_clip,
        duration=1.0,
        fps=60,
        motion_type=CameraMotionProfile.MACRO_PUSH_IN,
    )
    assert res.exists()
    assert res.stat().st_size > 1000

    info = ffprobe_json(res)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert video["width"] == 1080
    assert video["height"] == 1920
    # Framerate check
    r_fps = video.get("r_frame_rate", "")
    num, den = r_fps.split("/")
    fps = float(num) / float(den)
    assert fps == 60.0
