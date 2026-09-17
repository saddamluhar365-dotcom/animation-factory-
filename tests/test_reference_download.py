from pathlib import Path
import sys
import types

import app.reference as reference


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
        return {"id": "reference123", "ext": "mp4"}

    def prepare_filename(self, info):
        return str(reference.REF_DIR / "reference123.mp4")


def test_youtube_download_retries_with_chrome_cookies(monkeypatch):
    _FakeYoutubeDL.options_seen = []
    _FakeYoutubeDL.calls = 0
    fake_module = types.SimpleNamespace(YoutubeDL=_FakeYoutubeDL)
    monkeypatch.setitem(sys.modules, "yt_dlp", fake_module)
    monkeypatch.setattr(reference.shutil, "which", lambda name: "node.exe" if name == "node" else None)

    result = reference.download_reference_url("https://www.youtube.com/shorts/reference123")

    assert result == Path(reference.REF_DIR / "reference123.mp4")
    assert _FakeYoutubeDL.calls == 2
    assert _FakeYoutubeDL.options_seen[0]["js_runtimes"] == {"node": {}}
    assert "cookiesfrombrowser" not in _FakeYoutubeDL.options_seen[0]
    assert _FakeYoutubeDL.options_seen[1]["cookiesfrombrowser"] == ("chrome",)
    assert _FakeYoutubeDL.options_seen[1]["js_runtimes"] == {"node": {}}


def test_youtube_download_error_is_actionable(monkeypatch):
    class FailingYoutubeDL(_FakeYoutubeDL):
        def extract_info(self, url, download=True):
            raise RuntimeError("HTTP Error 429: Too Many Requests")

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=FailingYoutubeDL))
    monkeypatch.setattr(reference.shutil, "which", lambda name: "node.exe" if name == "node" else None)

    try:
        reference.download_reference_url("https://www.youtube.com/shorts/rate-limited")
    except RuntimeError as exc:
        assert "rate-limited" in str(exc).lower()
        assert "429" in str(exc)
    else:
        raise AssertionError("Expected an actionable HTTP 429 error")
