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


def _yt_dlp_options(*, browser_cookies: bool = False) -> dict:
    options = {
        "outtmpl": str(REF_DIR / "%(id)s.%(ext)s"),
        "format": "mp4/best",
        "noplaylist": True,
        "quiet": True,
        "socket_timeout": 20,
        "retries": 3,
        "fragment_retries": 3,
    }
    node = shutil.which("node")
    if node:
        options["js_runtimes"] = {"node": {}}
    if browser_cookies:
        options["cookiesfrombrowser"] = ("chrome",)
    return options


def _is_youtube_auth_or_rate_limit_error(exc: Exception) -> bool:
    message = str(exc).lower()
    markers = (
        "http error 429",
        "too many requests",
        "sign in to confirm you're not a bot",
        "sign in to confirm you’re not a bot",
        "use --cookies-from-browser",
        "confirm you're not a bot",
    )
    return any(marker in message for marker in markers)


def _reference_download_error(exc: Exception) -> RuntimeError:
    message = str(exc)
    lower = message.lower()
    if "sign in to confirm" in lower or "cookies-from-browser" in lower or "not a bot" in lower:
        return RuntimeError(
            "YouTube blocked this reference download with a bot/login check. "
            "The app retried with your Chrome cookies. Open this Short in Chrome, "
            "make sure YouTube is signed in and any CAPTCHA is completed, then try Add URL again. "
            "If YouTube still blocks it, use Upload / Add Video Files instead."
        )
    if "http error 429" in lower or "too many requests" in lower:
        return RuntimeError(
            "YouTube rate-limited this download (HTTP 429). Wait briefly and retry, or use "
            "Upload / Add Video Files for the reference Short."
        )
    return RuntimeError(f"Reference download failed: {message}")


def download_reference_url(url: str) -> Path:
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError("yt-dlp is required for Shorts URL download") from exc

    first_error: Exception | None = None
    for use_browser_cookies in (False, True):
        if use_browser_cookies and first_error is not None and not _is_youtube_auth_or_rate_limit_error(first_error):
            break
        try:
            with yt_dlp.YoutubeDL(_yt_dlp_options(browser_cookies=use_browser_cookies)) as ydl:
                info = ydl.extract_info(url, download=True)
                return Path(ydl.prepare_filename(info))
        except Exception as exc:
            first_error = exc
            if not use_browser_cookies:
                continue
            raise _reference_download_error(exc) from exc

    if first_error is not None:
        raise _reference_download_error(first_error) from first_error
    raise RuntimeError("Reference download failed without a diagnostic error")


def probe_video(path: Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {"file": path.name, "ffprobe": False}
    try:
        out = subprocess.check_output(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=width,height,r_frame_rate",
                "-of",
                "json",
                str(path),
            ],
            text=True,
        )
        return json.loads(out)
    except Exception as exc:
        return {"file": path.name, "error": str(exc)}


def extract_frame(path: Path, output: Path, second: float = 1.0) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required for reference frame extraction")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-ss",
            str(second),
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(output),
        ],
        check=True,
        capture_output=True,
    )
    return output


def analyze_reference(path: Path) -> dict:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(path)
    metadata = probe_video(path)
    frame = REF_DIR / f"{path.stem}_sample.jpg"
    try:
        extract_frame(path, frame)
        visual = gemini_image_analysis(
            frame.read_bytes(),
            "Analyze this reference short frame for high-level production style: art style, character design, environment, camera, lighting, color, composition, animation feel, pacing cues and mood. Do not identify or reproduce the creator or protected characters.",
        )
    except Exception as exc:
        visual = f"Visual AI analysis unavailable: {exc}"
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "file": path.name,
        "source_hash": source_hash,
        "metadata": metadata,
        "visual_analysis": visual,
    }


def save_reference_profile(results: list[dict]) -> None:
    config = load_config()
    profile = {
        "references": results,
        "instruction": "Use references only as high-level production guidance. Generate original stories and assets; do not copy protected characters, scenes, dialogue, or shot-for-shot sequences.",
    }
    config["reference_profile"] = profile
    config["initialized"] = True
    save_config(config)

    db = MemoryDB()
    db.remember_reference(
        profile,
        source_hash=hashlib.sha256(
            json.dumps(profile, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest(),
    )
    db.remember_style_dna(profile)
