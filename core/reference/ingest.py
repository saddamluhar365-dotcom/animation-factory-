from __future__ import annotations
import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse


def is_youtube_url(value: str) -> bool:
    host = urlparse(value).netloc.lower().split(":")[0]
    return host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}


def validate_source(source: str | Path) -> None:
    if isinstance(source, Path):
        if not source.is_file():
            raise FileNotFoundError(source)
        return
    if not is_youtube_url(source):
        raise ValueError("Reference URL must be a supported public YouTube/Shorts URL")


def content_hash(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def youtube_video_id(url: str) -> str | None:
    patterns = [r"[?&]v=([\w-]{11})", r"youtu\.be/([\w-]{11})", r"/shorts/([\w-]{11})"]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None
