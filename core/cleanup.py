from __future__ import annotations

import shutil
from pathlib import Path


def cleanup_project_artifacts(project_dir: Path, final_video: Path, output_dir: Path) -> None:
    """Remove a completed project's temporary artifacts while preserving its final MP4.

    Cleanup is intentionally performed only after final output QC succeeds. The final
    video must live outside the temporary project directory and inside the configured
    output directory before the project directory can be removed.
    """
    project_dir = project_dir.resolve()
    final_video = final_video.resolve()
    output_dir = output_dir.resolve()

    if not final_video.is_file():
        raise FileNotFoundError(f"Final video does not exist: {final_video}")
    if output_dir not in final_video.parents:
        raise ValueError("Final video must be stored inside the output directory")
    if project_dir == output_dir or project_dir in output_dir.parents:
        raise ValueError("Refusing to remove an output directory or its parent")
    if final_video.is_relative_to(project_dir):
        raise ValueError("Final video must not be inside the temporary project directory")

    shutil.rmtree(project_dir)


def cleanup_output_directory(output_dir: Path, keep_extensions: tuple[str, ...] = (".mp4",)) -> int:
    """Remove non-final artifacts from the main output directory.

    Returns the number of files removed. By default only MP4 files are retained.
    """
    output_dir = output_dir.resolve()
    if not output_dir.exists():
        return 0

    removed = 0
    for path in output_dir.iterdir():
        if path.is_file() and path.suffix.lower() not in keep_extensions:
            path.unlink()
            removed += 1
        elif path.is_dir():
            shutil.rmtree(path)
            removed += 1
    return removed
