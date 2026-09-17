from __future__ import annotations
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from .providers import gemini_image_analysis
from .storage import load_config, save_config
from core.db.memory import MemoryDB

ROOT = Path(__file__).resolve().parent.parent
REF_DIR = ROOT / "assets" / "references"
REF_DIR.mkdir(parents=True, exist_ok=True)


def download_reference_url(url: str) -> Path:
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError("yt-dlp is required for Shorts URL download") from exc
    opts = {
        "outtmpl": str(REF_DIR / "%(id)s.%(ext)s"),
        "format": "mp4/best",
        "noplaylist": True,
        "quiet": True,
        "socket_timeout": 20,
        "retries": 3,
        "fragment_retries": 3,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return Path(ydl.prepare_filename(info))


def probe_video(path: Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {"file": path.name, "ffprobe": False}
    try:
        out = subprocess.check_output([ffprobe, "-v", "error", "-show_entries", "format=duration:stream=width,height,r_frame_rate", "-of", "json", str(path)], text=True)
        return json.loads(out)
    except Exception as exc:
        return {"file": path.name, "error": str(exc)}


def extract_frame(path: Path, output: Path, second: float = 1.0) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required for reference frame extraction")
    subprocess.run([ffmpeg, "-y", "-ss", str(second), "-i", str(path), "-frames:v", "1", "-q:v", "3", str(output)], check=True, capture_output=True)
    return output


def analyze_reference(path: Path) -> dict:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(path)
    metadata = probe_video(path)
    frame = REF_DIR / f"{path.stem}_sample.jpg"
    try:
        extract_frame(path, frame)
        visual = gemini_image_analysis(frame.read_bytes(), "Analyze this reference short frame for high-level production style: art style, character design, environment, camera, lighting, color, composition, animation feel, pacing cues and mood. Do not identify or reproduce the creator or protected characters.")
    except Exception as exc:
        visual = f"Visual AI analysis unavailable: {exc}"
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"file": path.name, "source_hash": source_hash, "metadata": metadata, "visual_analysis": visual}


def save_reference_profile(results: list[dict]) -> None:
    config = load_config()
    profile = {"references": results, "instruction": "Use references only as high-level production guidance. Generate original stories and assets; do not copy protected characters, scenes, dialogue, or shot-for-shot sequences."}
    config["reference_profile"] = profile
    config["initialized"] = True
    save_config(config)

    db = MemoryDB()
    db.remember_reference(profile, source_hash=hashlib.sha256(json.dumps(profile, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest())
    db.remember_style_dna(profile)
