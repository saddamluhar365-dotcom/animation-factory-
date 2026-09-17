from __future__ import annotations
import json
import shutil
import subprocess
from pathlib import Path
from .providers import gemini_image_analysis
from .storage import load_config, save_config

ROOT = Path(__file__).resolve().parent.parent
REF_DIR = ROOT / "assets" / "references"
REF_DIR.mkdir(parents=True, exist_ok=True)


def probe_video(path: Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {"file": path.name, "ffprobe": False}
    try:
        out = subprocess.check_output([ffprobe,"-v","error","-show_entries","format=duration:stream=width,height,r_frame_rate","-of","json",str(path)], text=True)
        return json.loads(out)
    except Exception as exc:
        return {"file": path.name, "error": str(exc)}


def extract_frame(path: Path, output: Path, second: float = 1.0) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required for reference frame extraction")
    subprocess.run([ffmpeg,"-y","-ss",str(second),"-i",str(path),"-frames:v","1","-q:v","3",str(output)], check=True, capture_output=True)
    return output


def analyze_reference(path: Path) -> dict:
    metadata = probe_video(path)
    frame = REF_DIR / f"{path.stem}_sample.jpg"
    visual = ""
    try:
        extract_frame(path, frame)
        visual = gemini_image_analysis(frame.read_bytes(), "Analyze this reference short frame for visual production style. Return concise observations for art style, character design, environment, camera, lighting, color, composition, animation feel, and mood. Do not identify or reproduce the creator.")
    except Exception as exc:
        visual = f"Visual AI analysis unavailable: {exc}"
    return {"file": path.name, "metadata": metadata, "visual_analysis": visual}


def save_reference_profile(results: list[dict]) -> None:
    config = load_config()
    profile = {
        "references": results,
        "instruction": "Use references only as high-level production guidance. Generate original stories and assets; do not copy protected characters, scenes, dialogue, or shot-for-shot sequences."
    }
    config["reference_profile"] = profile
    config["initialized"] = True
    save_config(config)
