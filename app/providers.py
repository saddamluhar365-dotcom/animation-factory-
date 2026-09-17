from __future__ import annotations

import base64
import json
import os
from typing import Any

import requests

from .storage import get_keys, set_api

TIMEOUT = 45
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"


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


def _gemini_generate(key: str, contents: list[dict[str, Any]], timeout: int = TIMEOUT) -> requests.Response:
    url = f"{GEMINI_BASE_URL}/models/{_gemini_model()}:generateContent"
    return requests.post(url, headers=_gemini_headers(key), json={"contents": contents}, timeout=timeout)


def test_gemini(key: str) -> tuple[bool, str]:
    try:
        response = _gemini_generate(key, [{"parts": [{"text": "Reply only OK."}]}], timeout=TIMEOUT)
        if not response.ok:
            return False, _format_http_error(response)
        return True, _gemini_text_from_response(response).strip() or "Gemini responded successfully"
    except requests.RequestException as exc:
        return False, f"Network error: {exc}"
    except RuntimeError as exc:
        return False, str(exc)


def test_hf(key: str) -> tuple[bool, str]:
    url = "https://huggingface.co/api/whoami-v2"
    r = requests.get(url, headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT)
    return r.ok, r.text[:300]


def test_tavily(key: str) -> tuple[bool, str]:
    url = "https://api.tavily.com/search"
    r = requests.post(url, json={"api_key": key, "query": "test", "max_results": 1}, timeout=TIMEOUT)
    return r.ok, r.text[:300]


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
            response = _gemini_generate(key, [{"parts": [{"text": prompt}]}], timeout=90)
            if response.ok:
                return _gemini_text_from_response(response)
            last = _format_http_error(response)
        except requests.RequestException as exc:
            last = f"Network error: {exc}"
        except RuntimeError as exc:
            last = str(exc)
    raise RuntimeError(f"Gemini generation failed: {last}")


def gemini_image_analysis(image_bytes: bytes, prompt: str) -> str:
    keys = get_keys("gemini")
    encoded = base64.b64encode(image_bytes).decode()
    last = "No Gemini key configured"
    for key in keys:
        try:
            response = _gemini_generate(
                key,
                [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": encoded}}]}],
                timeout=90,
            )
            if response.ok:
                return _gemini_text_from_response(response)
            last = _format_http_error(response)
        except requests.RequestException as exc:
            last = f"Network error: {exc}"
        except RuntimeError as exc:
            last = str(exc)
    raise RuntimeError(f"Gemini image analysis failed: {last}")


def hf_text_to_image(prompt: str, model: str = "black-forest-labs/FLUX.1-schnell") -> bytes:
    keys = get_keys("huggingface")
    last = "No Hugging Face token configured"
    for key in keys:
        try:
            url = f"https://router.huggingface.co/hf-inference/models/{model}"
            r = requests.post(url, headers={"Authorization": f"Bearer {key}"}, json={"inputs": prompt}, timeout=180)
            if r.ok and r.headers.get("content-type", "").startswith("image/"):
                return r.content
            last = r.text[:500]
        except Exception as exc:
            last = str(exc)
    raise RuntimeError(last)


def tavily_search(query: str) -> list[dict]:
    for key in get_keys("tavily"):
        try:
            r = requests.post("https://api.tavily.com/search", json={"api_key": key, "query": query, "max_results": 5}, timeout=45)
            if r.ok:
                return r.json().get("results", [])
        except requests.RequestException:
            continue
    return []
