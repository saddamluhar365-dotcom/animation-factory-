from __future__ import annotations
import json
import shutil
import subprocess
from pathlib import Path


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("FFmpeg is required and must be available on PATH")
    return path


def probe(path: Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe is required and must be available on PATH")
    p = subprocess.run([ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)], capture_output=True, text=True, check=True)
    data = json.loads(p.stdout)
    fmt = data.get("format", {})
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), {})
    return {"path": str(path), "duration": float(fmt.get("duration", 0) or 0), "format": fmt.get("format_name"), "size": int(fmt.get("size", 0) or 0), "width": video.get("width"), "height": video.get("height"), "fps": _fps(video.get("r_frame_rate")), "video_codec": video.get("codec_name"), "audio_codec": audio.get("codec_name"), "has_audio": bool(audio)}


def _fps(rate: str | None) -> float | None:
    if not rate or rate == "0/0":
        return None
    try:
        a, b = rate.split("/")
        return round(float(a) / float(b), 3) if float(b) else None
    except (ValueError, ZeroDivisionError):
        return None


def extract_frames(path: Path, out_dir: Path, count: int = 24) -> list[Path]:
    meta = probe(path)
    duration = max(meta["duration"], 0.1)
    out_dir.mkdir(parents=True, exist_ok=True)
    fps = max(1, count) / duration
    pattern = out_dir / "frame_%04d.jpg"
    subprocess.run([_ffmpeg(), "-y", "-i", str(path), "-vf", f"fps={fps}", "-q:v", "3", "-frames:v", str(count), str(pattern)], capture_output=True, check=True)
    return sorted(out_dir.glob("frame_*.jpg"))


def extract_audio(path: Path, out_file: Path) -> Path | None:
    meta = probe(path)
    if not meta["has_audio"]:
        return None
    out_file.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([_ffmpeg(), "-y", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out_file)], capture_output=True, check=True)
    return out_file
