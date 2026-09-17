from __future__ import annotations
import shutil
import subprocess
from pathlib import Path
from .ingest import validate_source


def download_public_youtube(url: str, destination: Path) -> Path:
    validate_source(url)
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        raise RuntimeError("yt-dlp is required for YouTube reference ingestion")
    destination.parent.mkdir(parents=True, exist_ok=True)
    template = str(destination.with_suffix("")) + ".%(ext)s"
    subprocess.run([ytdlp, "--no-playlist", "--merge-output-format", "mp4", "-o", template, url], check=True)
    candidates = sorted(destination.parent.glob(destination.stem + ".*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise RuntimeError("YouTube download produced no video file")
    return candidates[0]
