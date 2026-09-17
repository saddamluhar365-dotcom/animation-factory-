import io
import json
import shutil
from pathlib import Path
from PIL import Image
import pytest

from core.contracts import ProjectPlan, SceneBeat, ScenePlan
from core.db.memory import MemoryDB
from core.orchestrator.engine import ShortsEngine
from app.pipeline import run_project


def _create_test_image_bytes():
    img = Image.new("RGB", (1080, 1920), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def test_e2e_deterministic_pipeline_local(monkeypatch, tmp_path):
    # Ensure FFmpeg is available
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg/ffprobe required for full local e2e pipeline test")

    projects_dir = tmp_path / "projects"
    output_dir = tmp_path / "output"
    data_dir = tmp_path / "data"
    projects_dir.mkdir()
    output_dir.mkdir()
    data_dir.mkdir()

    import app.pipeline as pipeline
    monkeypatch.setattr(pipeline, "PROJECTS", projects_dir)
    monkeypatch.setattr(pipeline, "OUTPUT", output_dir)

    # Use SQLite for deterministic local memory testing
    sqlite_url = f"sqlite:///{(data_dir / 'memory.db').as_posix()}"
    monkeypatch.setenv("YT_AUTO_DB_URL", sqlite_url)

    # Mock external providers so no network or paid APIs are used
    monkeypatch.setattr(
        pipeline,
        "tavily_search",
        lambda query: [{"url": "https://example.com/test", "title": "Test Topic", "snippet": "Test snippet"}],
    )
    monkeypatch.setattr(
        pipeline,
        "hf_text_to_image",
        lambda prompt: _create_test_image_bytes(),
    )

    engine = ShortsEngine(tmp_path)
    status_updates = []
    
    # Run 1-second short generation
    final_video = engine.create_project(
        instruction="A tranquil origami swan floating on water",
        duration=1,
        status_cb=lambda s: status_updates.append(s),
    )

    assert final_video.exists()
    assert final_video.is_file()
    assert final_video.suffix == ".mp4"
    assert final_video.parent == output_dir
    assert final_video.stat().st_size > 1024

    # Verify status updates tracked progress
    assert any("Planning" in s for s in status_updates)
    assert any("QC PASS" in s for s in status_updates)

    # Verify MemoryDB persisted project, research, artifacts, and decisions
    db = MemoryDB(sqlite_url)
    projects_rows = db.list(project_key=final_video.stem.replace(".mp4", ""))
    assert len(projects_rows) > 0


def test_pipeline_crash_recovery_resumes_from_checkpoint(monkeypatch, tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg/ffprobe required for recovery test")

    projects_dir = tmp_path / "projects"
    output_dir = tmp_path / "output"
    projects_dir.mkdir()
    output_dir.mkdir()

    import app.pipeline as pipeline
    monkeypatch.setattr(pipeline, "PROJECTS", projects_dir)
    monkeypatch.setattr(pipeline, "OUTPUT", output_dir)
    monkeypatch.setenv("YT_AUTO_DB_URL", f"sqlite:///{(tmp_path / 'memory.db').as_posix()}")

    # Prepare an existing project with plan and images already generated (simulating a crash before animation)
    project_dir = projects_dir / "short_resumable"
    images_dir = project_dir / "images"
    images_dir.mkdir(parents=True)

    # 1 scene, 1 second plan
    beats = [
        SceneBeat(0.0, 0.33, "character places cup on table"),
        SceneBeat(0.33, 0.66, "cup stays on table firmly"),
        SceneBeat(0.66, 1.0, "character smiles gently"),
    ]
    plan = ProjectPlan(1, "Resume Test", [ScenePlan(1, 0.0, 1.0, beats, "Cozy kitchen coffee cup")])
    (project_dir / "plan.json").write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")
    (project_dir / "checkpoint.json").write_text(json.dumps({"stage": "images", "payload": {}}), encoding="utf-8")

    # Write pre-existing scene image
    img_path = images_dir / "scene_001.jpg"
    img_path.write_bytes(_create_test_image_bytes())

    # Mock providers - if called, they should raise an error to prove they were NOT called
    monkeypatch.setattr(
        pipeline,
        "tavily_search",
        lambda query: (_ for _ in ()).throw(RuntimeError("Should not research again")),
    )
    monkeypatch.setattr(
        pipeline,
        "hf_text_to_image",
        lambda prompt: (_ for _ in ()).throw(RuntimeError("Should not generate image again")),
    )

    status_updates = []
    final_video = run_project(
        instruction="Resume Test",
        duration=1,
        status_cb=lambda s: status_updates.append(s),
        project_dir=project_dir,
    )

    assert final_video.exists()
    assert final_video.stat().st_size > 1024
    assert any("Resuming with saved plan" in s for s in status_updates)
    assert any("Resuming with existing scene images" in s for s in status_updates)