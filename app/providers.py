from __future__ import annotations

import base64
import json
import os
import time
from typing import Any

import requests

from .storage import get_keys, set_api

TIMEOUT = 45
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
FALLBACK_GEMINI_MODELS = (
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
)
RETRYABLE_GEMINI_STATUS = {429, 500, 502, 503, 504}
MAX_GEMINI_RETRIES = 2


def _gemini_model() -> str:
    return os.getenv("YT_AUTO_GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL


def _gemini_headers(key: str) -> dict[str, str]:
    return {"Content-Type": "application/json", "x-goog-api-key": key}


def _format_http_error(response: requests.Response) -> str:
    try:
        payload: Any = response.json()
    except (ValueError, json.JSONDecodeError):
        payload = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            status = error.get("status")
            message = error.get("message")
            code = error.get("code", response.status_code)
            details = f"HTTP {code}"
            if status:
                details += f" {status}"
            if message:
                details += f": {message}"
            return details[:800]
    body = (response.text or "").strip().replace("\n", " ")
    return f"HTTP {response.status_code}: {body[:700]}" if body else f"HTTP {response.status_code}"


def _gemini_text_from_response(response: requests.Response) -> str:
    if not response.ok:
        raise RuntimeError(_format_http_error(response))
    try:
        payload = response.json()
        return payload["candidates"][0]["content"]["parts"][0]["text"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Gemini returned an unexpected response format") from exc


def _discover_gemini_models(key: str) -> list[str]:
    """Return generateContent-capable models, preferring the configured model."""
    preferred = _gemini_model()
    try:
        response = requests.get(
            f"{GEMINI_BASE_URL}/models",
            headers={"x-goog-api-key": key},
            timeout=TIMEOUT,
        )
        if response.ok:
            models = response.json().get("models", [])
            discovered: list[str] = []
            for item in models:
                methods = item.get("supportedGenerationMethods", [])
                name = str(item.get("name", "")).removeprefix("models/")
                if name and "generateContent" in methods:
                    discovered.append(name)
            ordered = []
            for name in (preferred, *FALLBACK_GEMINI_MODELS, *discovered):
                if name in discovered and name not in ordered:
                    ordered.append(name)
            return ordered
    except (requests.RequestException, ValueError, TypeError):
        pass
    return list(dict.fromkeys((preferred, *FALLBACK_GEMINI_MODELS)))


def _gemini_generate(
    key: str,
    contents: list[dict[str, Any]],
    model: str | None = None,
    timeout: int = TIMEOUT,
) -> requests.Response:
    selected_model = model or _gemini_model()
    url = f"{GEMINI_BASE_URL}/models/{selected_model}:generateContent"
    last_response: requests.Response | None = None
    for attempt in range(MAX_GEMINI_RETRIES + 1):
        try:
            response = requests.post(
                url,
                headers=_gemini_headers(key),
                json={"contents": contents},
                timeout=timeout,
            )
            last_response = response
            if response.status_code not in RETRYABLE_GEMINI_STATUS or attempt >= MAX_GEMINI_RETRIES:
                return response
            retry_after = response.headers.get("Retry-After")
            try:
                delay = min(8.0, max(0.5, float(retry_after))) if retry_after else min(8.0, 1.5**attempt)
            except ValueError:
                delay = min(8.0, 1.5**attempt)
            time.sleep(delay)
        except requests.RequestException:
            if attempt >= MAX_GEMINI_RETRIES:
                raise
            time.sleep(min(8.0, 1.5**attempt))
    if last_response is None:
        raise RuntimeError("Gemini request produced no response")
    return last_response


def _gemini_request_with_fallback(
    key: str,
    contents: list[dict[str, Any]],
    timeout: int,
) -> tuple[requests.Response, str]:
    last_response: requests.Response | None = None
    last_model = _gemini_model()
    for model in _discover_gemini_models(key):
        response = _gemini_generate(key, contents, model=model, timeout=timeout)
        last_response = response
        last_model = model
        if response.ok:
            return response, model
        if response.status_code not in RETRYABLE_GEMINI_STATUS:
            return response, model
    if last_response is None:
        raise RuntimeError("Gemini model discovery returned no usable models")
    return last_response, last_model


def test_gemini(key: str) -> tuple[bool, str]:
    try:
        response, model = _gemini_request_with_fallback(
            key,
            [{"parts": [{"text": "Reply only OK."}]}],
            timeout=TIMEOUT,
        )
        if not response.ok:
            return False, f"{_format_http_error(response)} [model={model}]"
        return True, f"{_gemini_text_from_response(response).strip() or 'Gemini responded successfully'} [model={model}]"
    except requests.RequestException as exc:
        return False, f"Network error: {exc}"
    except RuntimeError as exc:
        return False, str(exc)


def test_hf(key: str) -> tuple[bool, str]:
    from core.image.router import HuggingFaceImageRouter
    url = "https://huggingface.co/api/whoami-v2"
    try:
        r = requests.get(url, headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT)
        if not r.ok:
            if r.status_code in (401, 403):
                return False, f"Hugging Face — INVALID_TOKEN: {r.text[:120].strip()}"
            return False, f"Hugging Face — {_format_http_error(r)}"

        try:
            name = r.json().get("name") or "user"
        except Exception:
            name = "user"

        router = HuggingFaceImageRouter(api_keys=[key])
        routes = router.candidate_routes()
        if not routes:
            return False, "Hugging Face — MODEL_UNAVAILABLE: no active text-to-image routes available"

        primary_model, primary_provider = routes[0]
        return True, f"Hugging Face — Image Generation: LIVE (@{name}, model={primary_model}, provider={primary_provider})"
    except requests.RequestException as exc:
        return False, f"Network error: {exc}"


def register(provider: str, key: str) -> tuple[bool, str]:
    tests = {"gemini": test_gemini, "huggingface": test_hf, "tavily": test_tavily}
    fn = tests.get(provider)
    if not fn:
        return False, "Unknown provider"
    ok, msg = fn(key)
    if ok:
        set_api(provider, key)
    return ok, msg


def gemini_text(prompt: str) -> str:
    keys = get_keys("gemini")
    last = "No Gemini key configured"
    for key in keys:
        try:
            response, model = _gemini_request_with_fallback(
                key,
                [{"parts": [{"text": prompt}]}],
                timeout=90,
            )
            if response.ok:
                return _gemini_text_from_response(response)
            last = f"{_format_http_error(response)} [model={model}]"
        except requests.RequestException as exc:
            last = f"Network error: {exc}"
        except RuntimeError as exc:
            last = str(exc)
    raise RuntimeError(f"Gemini generation failed: {last}")


def gemini_image_analysis(image_bytes: bytes, prompt: str) -> str:
    keys = get_keys("gemini")
    encoded = base64.b64encode(image_bytes).decode()
    last = "No Gemini key configured"
    contents = [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": encoded}}]}]
    for key in keys:
        try:
            response, model = _gemini_request_with_fallback(key, contents, timeout=90)
            if response.ok:
                return _gemini_text_from_response(response)
            last = f"{_format_http_error(response)} [model={model}]"
        except requests.RequestException as exc:
            last = f"Network error: {exc}"
        except RuntimeError as exc:
            last = str(exc)
    raise RuntimeError(f"Gemini image analysis failed: {last}")


def hf_text_to_image(prompt: str, model: str | None = None) -> bytes:
    from pathlib import Path
    import tempfile
    from core.image.router import HuggingFaceImageRouter

    keys = get_keys("huggingface")
    if not keys:
        raise RuntimeError("Hugging Face image generation failed: No Hugging Face token configured")

    preferred = [model] if model else None
    router = HuggingFaceImageRouter(api_keys=keys, preferred_models=preferred)
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        router.generate(prompt=prompt, output_path=tmp_path)
        return tmp_path.read_bytes()
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def tavily_search(query: str) -> list[dict]:
    for key in get_keys("tavily"):
        try:
            r = requests.post("https://api.tavily.com/search", json={"api_key": key, "query": query, "max_results": 5}, timeout=45)
            if r.ok:
                return r.json().get("results", [])
        except requests.RequestException:
            continue
    return []
