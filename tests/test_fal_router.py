from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock
import pytest
import requests
from core.video.contracts import VideoGenerationRequest
from core.video.pool import FalKeyPool
from core.video.router import FalVideoRouter, PREFERRED_FAL_VIDEO_MODELS
from core.video.client import FalHttpClient


def test_fal_router_candidate_models():
    router = FalVideoRouter(api_keys=["fal_k1", "fal_k2"])
    models = router.candidate_models()
    assert len(models) >= 3
    assert "fal-ai/kling-video/v1/standard/text-to-video" in models

    # Mark first model deprecated
    first = models[0]
    router.mark_model_deprecated(first)
    assert first not in router.candidate_models()


def test_fal_router_rotates_on_429(tmp_path: Path):
    mock_client = MagicMock(spec=FalHttpClient)
    pool = FalKeyPool(keys=["key_429", "key_healthy"], default_cooldown=5.0)

    # First call with key_429 returns 429
    resp_429 = requests.Response()
    resp_429.status_code = 429

    # Second call with key_healthy succeeds
    resp_ok = requests.Response()
    resp_ok.status_code = 200
    resp_ok._content = b'{"video": {"url": "https://example.com/fake.mp4"}}'

    mock_client.submit_job.side_effect = [resp_429, resp_ok]
    
    # Download writes fake video
    def fake_download(url, path):
        path.write_bytes(b"mock_mp4_video_data_1234567890" * 50)
        return path
    mock_client.download_video.side_effect = fake_download

    router = FalVideoRouter(pool=pool, client=mock_client)
    out_clip = tmp_path / "scene_001.mp4"
    req = VideoGenerationRequest("test prompt", duration=2.0)

    result = router.generate(req, out_clip)
    assert result.status == "success"
    assert result.provider == "fal_video"
    assert mock_client.submit_job.call_count == 2
    assert pool.status_summary()["rate_limited"] == 1


def test_fal_router_disables_on_401(tmp_path: Path):
    mock_client = MagicMock(spec=FalHttpClient)
    pool = FalKeyPool(keys=["invalid_key", "good_key"])

    resp_401 = requests.Response()
    resp_401.status_code = 401
    resp_401._content = b'{"detail": "Invalid API Key"}'

    resp_ok = requests.Response()
    resp_ok.status_code = 200
    resp_ok._content = b'{"video": {"url": "https://example.com/video.mp4"}}'

    mock_client.submit_job.side_effect = [resp_401, resp_ok]
    mock_client.download_video.side_effect = lambda u, p: (p.write_bytes(b"mp4_content" * 100), p)[1]

    router = FalVideoRouter(pool=pool, client=mock_client)
    out_clip = tmp_path / "scene_001.mp4"
    req = VideoGenerationRequest("test prompt", duration=2.0)

    result = router.generate(req, out_clip)
    assert result.status == "success"
    assert pool.status_summary()["invalid"] == 1


def test_fal_router_production_raises_without_placeholders(tmp_path: Path):
    mock_client = MagicMock(spec=FalHttpClient)
    resp_err = requests.Response()
    resp_err.status_code = 500
    resp_err._content = b'{"error": "Internal Server Error"}'
    mock_client.submit_job.return_value = resp_err

    router = FalVideoRouter(api_keys=["fal_k1"], client=mock_client)
    out_clip = tmp_path / "scene_001.mp4"
    req = VideoGenerationRequest("test prompt", duration=2.0)

    # In production, allow_placeholders is False -> must raise
    with pytest.raises(RuntimeError, match="FAL Video generation failed"):
        router.generate(req, out_clip, allow_placeholders=False)
