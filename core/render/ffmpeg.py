from __future__ import annotations
import shutil
import subprocess
from pathlib import Path


def ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path: raise RuntimeError("FFmpeg is required and must be available on PATH")
    return path


def animate_image(image: Path, output: Path, duration: float, fps: int = 24) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,zoompan=z='min(zoom+0.0008,1.08)':d=1:s=1080x1920:fps=%d,format=yuv420p" % fps
    subprocess.run([ffmpeg(), "-y", "-loop", "1", "-i", str(image), "-t", f"{duration:.3f}", "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", str(output)], capture_output=True, check=True)
    return output


def concat(clips: list[Path], output: Path) -> Path:
    if not clips: raise ValueError("No clips to render")
    manifest = output.with_suffix(".concat.txt")
    manifest.write_text("\n".join(f"file '{p.resolve().as_posix().replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'" for p in clips), encoding="utf-8")
    subprocess.run([ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c", "copy", "-movflags", "+faststart", str(output)], capture_output=True, check=True)
    return output
