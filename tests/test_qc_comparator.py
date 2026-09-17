from __future__ import annotations
import shutil
from pathlib import Path
from PIL import Image
import pytest
from core.contracts import ProjectPlan, SceneBeat, ScenePlan
from core.qc.comparator import ReferenceQCComparator, compare_reference_to_output
from core.render.ffmpeg import animate_image, concat, mux_video_audio, synthesize_audio
from core.audio.timeline import AudioEvent, AudioTimeline


def test_qc_comparator_with_generated_output(tmp_path: Path):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg not available")

    # Generate a small 60 FPS 2-scene vertical video
    img1 = tmp_path / "img1.jpg"
    img2 = tmp_path / "img2.jpg"
    Image.new("RGB", (1080, 1920), (140, 100, 60)).save(img1)
    Image.new("RGB", (1080, 1920), (160, 120, 80)).save(img2)

    clip1 = animate_image(img1, tmp_path / "c1.mp4", duration=1.5, fps=60)
    clip2 = animate_image(img2, tmp_path / "c2.mp4", duration=1.5, fps=60)
    silent = concat([clip1, clip2], tmp_path / "silent.mp4")

    timeline = AudioTimeline(3.0)
    timeline.add(AudioEvent(0.0, 3.0, "ambience", "environment", 0.20))
    timeline.add(AudioEvent(0.5, 1.2, "sfx", "sizzle", 0.25, True))
    audio = synthesize_audio(3.0, timeline, tmp_path / "audio.m4a")

    out_video = tmp_path / "final_short.mp4"
    mux_video_audio(silent, audio, out_video, 3.0)

    scenes = [
        ScenePlan(1, 0.0, 1.5, [SceneBeat(0.0, 0.5, "prep knife", "pan"), SceneBeat(0.5, 1.0, "slice", "push"), SceneBeat(1.0, 1.5, "rest", "pan")], "Original kitchen scene"),
        ScenePlan(2, 1.5, 3.0, [SceneBeat(1.5, 2.0, "sear", "push"), SceneBeat(2.0, 2.5, "flip", "tilt"), SceneBeat(2.5, 3.0, "serve", "reveal")], "Original plating scene"),
    ]
    plan = ProjectPlan(3, "Original Gourmet Pan Short", scenes, {}, {})

    ref_path = Path("assets/references/videoplayback.mp4")
    report = compare_reference_to_output(ref_path, out_video, plan=plan)

    assert report.aspect_ratio_match is True
    assert report.framerate_match is True
    assert report.output_fps == 60.0
    assert report.overall_fidelity_score >= 80.0
    assert report.protected_content_compliant is True
    assert report.passed is True
