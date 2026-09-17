from __future__ import annotations
import json
import shutil
import subprocess
from pathlib import Path
from core.qc.rules import validate_metadata
from core.qc.comparator import ReferenceQCComparator, QCComparisonReport, compare_reference_to_output


def ffprobe_json(path: Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe is required and must be available on PATH")
    p = subprocess.run([ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)], capture_output=True, text=True, check=True)
    return json.loads(p.stdout)


def ffprobe_duration(path: Path) -> float:
    return float(ffprobe_json(path).get("format", {}).get("duration", 0) or 0)


def validate_output(path: Path, requested_duration: float, tolerance: float = 0.08) -> list[str]:
    if not path.exists() or path.stat().st_size < 1024:
        return ["output missing or empty"]
    try:
        raw = ffprobe_json(path)
        fmt = raw.get("format", {})
        video = next((s for s in raw.get("streams", []) if s.get("codec_type") == "video"), {})
        audio = next((s for s in raw.get("streams", []) if s.get("codec_type") == "audio"), {})
        r_fps = video.get("r_frame_rate", "")
        fps = None
        if r_fps and "/" in r_fps:
            try:
                num, den = r_fps.split("/")
                fps = float(num) / float(den) if float(den) else None
            except (ValueError, ZeroDivisionError):
                pass
        meta = {
            "duration": float(fmt.get("duration", 0) or 0),
            "video_duration": float(video.get("duration") or fmt.get("duration") or 0),
            "audio_duration": float(audio.get("duration") or fmt.get("duration") or 0) if audio else 0.0,
            "width": video.get("width"),
            "height": video.get("height"),
            "fps": fps,
            "video_codec": video.get("codec_name"),
            "audio_codec": audio.get("codec_name"),
            "has_audio": bool(audio),
        }
        errors = validate_metadata(meta, requested_duration, tolerance)
        if meta["has_audio"]:
            errors.extend(_audio_clipping_check(path))
        errors.extend(_black_frame_check(path))
        return errors
    except Exception as exc:
        return [f"ffprobe/QC failed: {exc}"]


def _black_frame_check(path: Path) -> list[str]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return []
    p = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path), "-vf", "blackdetect=d=0.25:pic_th=0.98", "-an", "-f", "null", "-"], capture_output=True, text=True)
    hits = [line for line in (p.stderr + p.stdout).splitlines() if "black_start:" in line]
    return ["black frames detected"] if hits else []


def _audio_clipping_check(path: Path) -> list[str]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return []
    p = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    for line in (p.stderr + p.stdout).splitlines():
        if "max_volume:" in line:
            try:
                value = float(line.split("max_volume:", 1)[1].split(" dB", 1)[0].strip())
                return ["audio clipping detected"] if value >= -0.05 else []
            except ValueError:
                return []
    return []
