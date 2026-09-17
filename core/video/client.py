from __future__ import annotations
import json
import logging
import os
import shutil
import time
from pathlib import Path
import requests

logger = logging.getLogger(__name__)

TIMEOUT = 60
FAL_QUEUE_URL = "https://queue.fal.run"
FAL_SYNC_URL = "https://fal.run"


def test_fal_key(key: str, timeout: int = 15) -> tuple[bool, str]:
    """Test a FAL API key for validity without burning heavy video generation credits."""
    clean_key = (key or "").strip()
    if not clean_key:
        return False, "Key is empty"
    if len(clean_key) < 10:
        return False, "Key format invalid (too short)"

    headers = {"Authorization": f"Key {clean_key}", "Accept": "application/json"}
    
    # Check key by querying status endpoint or models API
    try:
        url = f"{FAL_QUEUE_URL}/fal-ai/fast-svd/text-to-video"
        # OPTIONS or GET on endpoint returns 401 if unauthorized, 200/405 if authorized
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code in (401, 403):
            return False, f"Authentication failed: HTTP {resp.status_code} Invalid FAL API Key"
        if resp.status_code in (200, 400, 404, 405, 422):
            return True, "FAL API Key verified active and authenticated"
        return True, f"FAL API Key validated (HTTP {resp.status_code})"
    except requests.RequestException as exc:
        return False, f"Network error during key verification: {exc}"


class FalHttpClient:
    """REST API client for submitting video jobs and downloading results."""

    def __init__(self, timeout: int = TIMEOUT):
        self.timeout = timeout

    def submit_job(
        self,
        model: str,
        prompt: str,
        api_key: str,
        duration: float = 3.0,
        aspect_ratio: str = "9:16",
        seed: int | None = None,
    ) -> requests.Response:
        url = f"{FAL_QUEUE_URL}/{model}"
        headers = {
            "Authorization": f"Key {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "duration": f"{duration:.1f}",
        }
        if seed is not None:
            payload["seed"] = seed

        return requests.post(url, headers=headers, json=payload, timeout=self.timeout)

    def poll_job(
        self,
        model: str,
        request_id: str,
        api_key: str,
        max_wait: float = 120.0,
        poll_interval: float = 3.0,
    ) -> dict:
        status_url = f"{FAL_QUEUE_URL}/{model}/requests/{request_id}/status"
        result_url = f"{FAL_QUEUE_URL}/{model}/requests/{request_id}"
        headers = {"Authorization": f"Key {api_key}", "Accept": "application/json"}
        start = time.time()

        while time.time() - start < max_wait:
            resp = requests.get(status_url, headers=headers, timeout=self.timeout)
            if not resp.ok:
                raise RuntimeError(f"FAL status check failed: HTTP {resp.status_code} {resp.text[:200]}")

            data = resp.json()
            status = data.get("status")
            if status == "COMPLETED":
                res = requests.get(result_url, headers=headers, timeout=self.timeout)
                if not res.ok:
                    raise RuntimeError(f"FAL fetch result failed: HTTP {res.status_code}")
                return res.json()
            elif status in ("FAILED", "CANCELLED"):
                error_msg = data.get("error") or "FAL video generation failed in queue"
                raise RuntimeError(f"FAL job {request_id} failed: {error_msg}")

            time.sleep(poll_interval)

        raise TimeoutError(f"FAL video generation exceeded max wait of {max_wait:.1f}s")

    def download_video(self, video_url: str, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        resp = requests.get(video_url, stream=True, timeout=self.timeout)
        if not resp.ok:
            raise RuntimeError(f"Failed to download video from {video_url}: HTTP {resp.status_code}")

        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
        return output_path
