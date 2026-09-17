from __future__ import annotations
import base64
import requests
from .storage import get_keys, set_api

TIMEOUT = 45


def test_gemini(key: str) -> tuple[bool, str]:
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    r = requests.post(url, params={"key": key}, json={"contents":[{"parts":[{"text":"Reply only OK."}]}]}, timeout=TIMEOUT)
    return r.ok, r.text[:300]


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
            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
            r = requests.post(url, params={"key": key}, json={"contents":[{"parts":[{"text":prompt}]}]}, timeout=90)
            if r.ok:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"]
            last = r.text[:500]
        except Exception as exc:
            last = str(exc)
    raise RuntimeError(last)


def gemini_image_analysis(image_bytes: bytes, prompt: str) -> str:
    keys = get_keys("gemini")
    encoded = base64.b64encode(image_bytes).decode()
    for key in keys:
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
        payload = {"contents":[{"parts":[{"text":prompt},{"inline_data":{"mime_type":"image/jpeg","data":encoded}}]}]}
        r = requests.post(url, params={"key": key}, json=payload, timeout=90)
        if r.ok:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    raise RuntimeError("All Gemini keys failed")


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
            r = requests.post("https://api.tavily.com/search", json={"api_key":key,"query":query,"max_results":5}, timeout=45)
            if r.ok:
                return r.json().get("results", [])
        except requests.RequestException:
            continue
    return []
