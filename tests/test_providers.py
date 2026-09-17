import json

from app import providers


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text if text is not None else json.dumps(self._payload)
        self.headers = headers or {"content-type": "application/json"}

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


def test_gemini_uses_current_header_auth_and_current_model(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeResponse(
            payload={
                "candidates": [
                    {"content": {"parts": [{"text": "OK"}]}}
                ]
            }
        )

    monkeypatch.setattr(providers.requests, "post", fake_post)

    ok, message = providers.test_gemini("secret-key")

    assert ok is True
    assert message == "OK"
    assert captured["url"].endswith("/models/gemini-3.8-flash:generateContent")
    assert captured["kwargs"]["headers"]["x-goog-api-key"] == "secret-key"
    assert "key" not in captured["kwargs"].get("params", {})
    assert captured["kwargs"]["headers"]["Content-Type"] == "application/json"


def test_gemini_failure_returns_actionable_http_error(monkeypatch):
    def fake_post(url, **kwargs):
        return FakeResponse(
            status_code=403,
            payload={
                "error": {
                    "code": 403,
                    "status": "PERMISSION_DENIED",
                    "message": "API key is not authorized for this API.",
                }
            },
        )

    monkeypatch.setattr(providers.requests, "post", fake_post)

    ok, message = providers.test_gemini("bad-key")

    assert ok is False
    assert "HTTP 403" in message
    assert "PERMISSION_DENIED" in message
    assert "not authorized" in message


def test_gemini_text_returns_response_text(monkeypatch):
    monkeypatch.setattr(providers, "get_keys", lambda provider: ["secret-key"])

    def fake_post(url, **kwargs):
        assert kwargs["headers"]["x-goog-api-key"] == "secret-key"
        return FakeResponse(
            payload={
                "candidates": [
                    {"content": {"parts": [{"text": "Generated story"}]}}
                ]
            }
        )

    monkeypatch.setattr(providers.requests, "post", fake_post)

    assert providers.gemini_text("make a short") == "Generated story"


def test_gemini_image_analysis_preserves_actionable_failure(monkeypatch):
    monkeypatch.setattr(providers, "get_keys", lambda provider: ["bad-key"])

    def fake_post(url, **kwargs):
        return FakeResponse(
            status_code=404,
            payload={
                "error": {
                    "code": 404,
                    "status": "NOT_FOUND",
                    "message": "Model not found",
                }
            },
        )

    monkeypatch.setattr(providers.requests, "post", fake_post)

    try:
        providers.gemini_image_analysis(b"image", "describe")
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected Gemini image analysis to fail")

    assert "HTTP 404" in message
    assert "NOT_FOUND" in message
    assert "Model not found" in message
