from pathlib import Path
import sys
import types
import pytest

import core.reference.youtube as youtube


class _FakeYoutubeDL:
    options_seen = []
    calls = 0

    def __init__(self, options):
        self.options = options
        type(self).options_seen.append(options)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def extract_info(self, url, download=True):
        type(self).calls += 1
        if "cookiesfrombrowser" not in self.options:
            raise RuntimeError("ERROR: [youtube] Sign in to confirm you're not a bot")
        return {"id": "ref123", "ext": "mp4"}

    def prepare_filename(self, info):
        return str(Path("dummy_dest.mp4"))


def test_core_youtube_download_retries_with_chrome_cookies(monkeypatch, tmp_path):
    _FakeYoutubeDL.options_seen = []
    _FakeYoutubeDL.calls = 0
    fake_module = types.SimpleNamespace(YoutubeDL=_FakeYoutubeDL)
    monkeypatch.setitem(sys.modules, "yt_dlp", fake_module)
    monkeypatch.setattr(youtube.shutil, "which", lambda name: "node.exe" if name == "node" else None)

    dest = tmp_path / "ref.mp4"
    dest.write_bytes(b"video content")
    monkeypatch.setattr(_FakeYoutubeDL, "prepare_filename", lambda self, info: str(dest))

    result = youtube.download_public_youtube("https://www.youtube.com/shorts/ref123", dest)
    assert result == dest
    assert _FakeYoutubeDL.calls == 2
    assert _FakeYoutubeDL.options_seen[0]["js_runtimes"] == {"node": {}}
    assert "cookiesfrombrowser" not in _FakeYoutubeDL.options_seen[0]
    assert _FakeYoutubeDL.options_seen[1]["cookiesfrombrowser"] == ("chrome",)


def test_core_youtube_download_rejects_invalid_url():
    with pytest.raises(ValueError, match="supported public YouTube/Shorts URL"):
        youtube.download_public_youtube("https://not-youtube.com/video", Path("out.mp4"))


def test_core_youtube_download_429_returns_actionable_message(monkeypatch, tmp_path):
    class RateLimitedYoutubeDL(_FakeYoutubeDL):
        def extract_info(self, url, download=True):
            raise RuntimeError("HTTP Error 429: Too Many Requests")

    fake_module = types.SimpleNamespace(YoutubeDL=RateLimitedYoutubeDL)
    monkeypatch.setitem(sys.modules, "yt_dlp", fake_module)

    dest = tmp_path / "ref.mp4"
    with pytest.raises(RuntimeError, match="rate-limited"):
        youtube.download_public_youtube("https://www.youtube.com/shorts/ref123", dest)