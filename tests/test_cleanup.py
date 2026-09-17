from pathlib import Path

from core.cleanup import cleanup_project_artifacts


def test_cleanup_removes_project_artifacts_but_preserves_final_video(tmp_path: Path):
    project = tmp_path / "short_001"
    output = tmp_path / "output"
    project.mkdir()
    output.mkdir()
    final_video = output / "short_001.mp4"
    final_video.write_bytes(b"final")

    (project / "images").mkdir()
    (project / "images" / "scene_001.jpg").write_bytes(b"image")
    (project / "clips").mkdir()
    (project / "clips" / "scene_001.mp4").write_bytes(b"clip")
    (project / "audio.wav.m4a").write_bytes(b"audio")
    (project / "plan.json").write_text("{}", encoding="utf-8")

    cleanup_project_artifacts(project, final_video, output)

    assert final_video.exists()
    assert not project.exists()
    assert list(output.iterdir()) == [final_video]
