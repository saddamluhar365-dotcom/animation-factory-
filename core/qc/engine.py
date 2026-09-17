from __future__ import annotations
import shutil
import subprocess
from pathlib import Path


def ffprobe_duration(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe: raise RuntimeError("ffprobe is required")
    p = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)], capture_output=True, text=True, check=True)
    return float(p.stdout.strip())


def validate_output(path: Path, requested_duration: float, tolerance: float = 0.08) -> list[str]:
    errors = []
    if not path.exists() or path.stat().st_size < 1024:
        return ["output missing or empty"]
    try: duration = ffprobe_duration(path)
    except Exception as exc: return [f"ffprobe failed: {exc}"]
    if abs(duration - requested_duration) > tolerance: errors.append(f"duration mismatch: {duration:.3f}s vs {requested_duration:.3f}s")
    return errors
