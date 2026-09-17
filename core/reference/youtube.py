from __future__ import annotations
import shutil
from pathlib import Path
from .ingest import validate_source


def _yt_dlp_options(destination: Path, *, browser_cookies: bool = False) -> dict:
    options = {
        "outtmpl": str(destination.with_suffix("")) + ".%(ext)s",
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


def download_public_youtube(url: str, destination: Path) -> Path:
    validate_source(url)
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError("yt-dlp is required for YouTube reference ingestion") from exc

    destination.parent.mkdir(parents=True, exist_ok=True)
    first_error: Exception | None = None
    for use_browser_cookies in (False, True):
        if use_browser_cookies and first_error is not None and not _is_youtube_auth_or_rate_limit_error(first_error):
            break
        try:
            with yt_dlp.YoutubeDL(_yt_dlp_options(destination, browser_cookies=use_browser_cookies)) as ydl:
                info = ydl.extract_info(url, download=True)
                prepared = Path(ydl.prepare_filename(info))
                if prepared.exists():
                    return prepared
                candidates = sorted(destination.parent.glob(destination.stem + ".*"), key=lambda p: p.stat().st_mtime, reverse=True)
                if candidates:
                    return candidates[0]
                raise RuntimeError("YouTube download produced no video file")
        except Exception as exc:
            first_error = exc
            if not use_browser_cookies:
                continue
            raise _reference_download_error(exc) from exc

    if first_error is not None:
        raise _reference_download_error(first_error) from first_error
    raise RuntimeError("Reference download failed without a diagnostic error")
