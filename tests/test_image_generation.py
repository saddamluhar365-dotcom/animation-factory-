from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
import pytest
from PIL import Image

from core.contracts import ProjectPlan, SceneBeat, ScenePlan
from core.image.contracts import ImageResult, ImageRouteStatus
from core.image.router import HuggingFaceImageRouter, generate_image
from core.image.validator import (
    ImageValidationError,
    ensure_vertical_shorts_dimensions,
    validate_image_bytes,
    validate_image_file,
)
from app.pipeline import _format_scene_prompt, generate_images


def _create_dummy_image(width: int = 1080, height: int = 1920) -> Image.Image:
    return Image.new("RGB", (width, height), (50, 100, 150))


# TEST 1: Successful image generation
def test_successful_image_generation(tmp_path: Path):
    router = HuggingFaceImageRouter(api_keys=["hf_test_token"])
    dummy = _create_dummy_image(1080, 1920)
    router._call_inference_client = MagicMock(return_value=dummy)

    target = tmp_path / "scene_001.jpg"
    res = router.generate("A cinematic shot of a character", output_path=target)

    assert isinstance(res, ImageResult)
    assert target.is_file()
    assert res.path == target
    assert res.model == router.preferred_models[0]
    w, h = validate_image_file(target)
    assert (w, h) == (1080, 1920)


# TEST 2: HTTP 410 deprecated model (old route invalidated, new compatible route selected)
def test_410_deprecated_model_invalidates_route(tmp_path: Path):
    HuggingFaceImageRouter._deprecated_routes.clear()
    router = HuggingFaceImageRouter(
        api_keys=["hf_test_token"],
        preferred_models=["black-forest-labs/FLUX.1-schnell", "black-forest-labs/FLUX.1-dev"],
        providers=["auto"],
    )

    call_history = []

    def fake_call(prompt, model, provider, api_key, **kwargs):
        call_history.append((model, provider))
        if model == "black-forest-labs/FLUX.1-schnell":
            # Simulate Hugging Face 410 deprecated model exception
            exc = RuntimeError("HTTP 410: The requested model is deprecated and no longer supported by provider hf-inference")
            exc.response = MagicMock(status_code=410)
            raise exc
        return _create_dummy_image(1080, 1920)

    router._call_inference_client = fake_call
    target = tmp_path / "scene_001.jpg"
    res = router.generate("A hero standing in the rain", output_path=target)

    # Old route is recorded as deprecated
    assert ("black-forest-labs/FLUX.1-schnell", "auto") in HuggingFaceImageRouter._deprecated_routes
    # New route succeeded
    assert res.model == "black-forest-labs/FLUX.1-dev"
    assert call_history == [
        ("black-forest-labs/FLUX.1-schnell", "auto"),
        ("black-forest-labs/FLUX.1-dev", "auto"),
    ]
    assert target.is_file()


# TEST 3: HTTP 429 rate limit handling and route/key rotation
def test_429_rate_limit_rotates_keys(tmp_path: Path):
    router = HuggingFaceImageRouter(
        api_keys=["key1_rate_limited", "key2_working"],
        preferred_models=["black-forest-labs/FLUX.1-dev"],
        providers=["auto"],
    )

    used_keys = []

    def fake_call(prompt, model, provider, api_key, **kwargs):
        used_keys.append(api_key)
        if api_key == "key1_rate_limited":
            exc = RuntimeError("HTTP 429: Too Many Requests")
            exc.response = MagicMock(status_code=429)
            raise exc
        return _create_dummy_image(1080, 1920)

    router._call_inference_client = fake_call
    target = tmp_path / "scene_001.jpg"
    res = router.generate("A sunny landscape", output_path=target)

    assert used_keys == ["key1_rate_limited", "key2_working"]
    assert res.model == "black-forest-labs/FLUX.1-dev"
    assert target.is_file()


# TEST 4: HTTP 503 retry / fallback
def test_503_temporary_failure_retries_and_falls_back(tmp_path: Path):
    HuggingFaceImageRouter._deprecated_routes.clear()
    router = HuggingFaceImageRouter(
        api_keys=["hf_test_token"],
        preferred_models=["black-forest-labs/FLUX.1-schnell", "black-forest-labs/FLUX.1-dev"],
        providers=["auto"],
    )

    def fake_call(prompt, model, provider, api_key, **kwargs):
        if model == "black-forest-labs/FLUX.1-schnell":
            exc = RuntimeError("HTTP 503: Service Unavailable / Model Loading")
            exc.response = MagicMock(status_code=503)
            raise exc
        return _create_dummy_image(1080, 1920)

    router._call_inference_client = fake_call
    target = tmp_path / "scene_001.jpg"
    res = router.generate("A quiet lake", output_path=target)

    assert res.model == "black-forest-labs/FLUX.1-dev"
    assert target.is_file()


# TEST 5: Invalid token produces clear authentication error
def test_invalid_token_reports_authentication_error(tmp_path: Path):
    router = HuggingFaceImageRouter(
        api_keys=["invalid_token_abc"],
        preferred_models=["black-forest-labs/FLUX.1-dev"],
        providers=["auto"],
    )

    def fake_call(prompt, model, provider, api_key, **kwargs):
        exc = RuntimeError("HTTP 401: Unauthorized: Invalid token")
        exc.response = MagicMock(status_code=401)
        raise exc

    router._call_inference_client = fake_call
    target = tmp_path / "scene_001.jpg"
    with pytest.raises(RuntimeError) as exc_info:
        router.generate("test prompt", output_path=target)

    assert "authentication error" in str(exc_info.value).lower()
    # Confirm secret token is not leaked in error message
    assert "invalid_token_abc" not in str(exc_info.value)


# TEST 6: Model unavailable resolves alternative
def test_model_unavailable_resolves_alternative(tmp_path: Path):
    HuggingFaceImageRouter._deprecated_routes.clear()
    router = HuggingFaceImageRouter(
        api_keys=["hf_test_token"],
        preferred_models=["model_unsupported", "stabilityai/stable-diffusion-3.5-large"],
        providers=["auto"],
    )

    def fake_call(prompt, model, provider, api_key, **kwargs):
        if model == "model_unsupported":
            raise RuntimeError("Model model_unsupported is not available for inference")
        return _create_dummy_image(1080, 1920)

    router._call_inference_client = fake_call
    target = tmp_path / "scene_001.jpg"
    res = router.generate("A futuristic city", output_path=target)

    assert res.model == "stabilityai/stable-diffusion-3.5-large"
    assert target.is_file()


# TEST 7: All image providers fail raises in production mode (NO placeholder)
def test_all_image_providers_fail_raises_in_production(tmp_path: Path):
    router = HuggingFaceImageRouter(
        api_keys=["hf_test_token"],
        preferred_models=["model_a"],
        providers=["auto"],
    )

    def fake_call(prompt, model, provider, api_key, **kwargs):
        raise RuntimeError("Service completely down")

    router._call_inference_client = fake_call
    target = tmp_path / "scene_001.jpg"

    # Production mode: allow_placeholders is False
    with pytest.raises(RuntimeError) as exc_info:
        router.generate("test prompt", output_path=target, allow_placeholders=False)

    assert "failed across all routes" in str(exc_info.value)
    # Target file should not have been created as a silent placeholder
    assert not target.exists()


# TEST 8: Development/test mode allows placeholder fixture
def test_development_mode_allows_placeholder_fixture(tmp_path: Path):
    router = HuggingFaceImageRouter(
        api_keys=["hf_test_token"],
        preferred_models=["model_a"],
        providers=["auto"],
    )

    def fake_call(prompt, model, provider, api_key, **kwargs):
        raise RuntimeError("Service down")

    router._call_inference_client = fake_call
    target = tmp_path / "scene_001.jpg"

    # In dev/test fixture mode: allow_placeholders=True
    res = router.generate("test prompt", output_path=target, allow_placeholders=True)

    assert res.model == "placeholder-fixture"
    assert res.metadata.get("placeholder") is True
    assert target.is_file()
    w, h = validate_image_file(target)
    assert (w, h) == (1080, 1920)


# TEST 9: Generated image is corrupt and caught by validator
def test_corrupted_image_caught_by_validator(tmp_path: Path):
    corrupted_data = b"<html><head><title>500 Internal Server Error</title></head></html>"
    with pytest.raises(ImageValidationError) as exc_info:
        validate_image_bytes(corrupted_data)
    assert "error payload" in str(exc_info.value).lower()

    corrupt_file = tmp_path / "bad.jpg"
    corrupt_file.write_bytes(b"short")
    with pytest.raises(ImageValidationError) as exc_info:
        validate_image_file(corrupt_file)
    assert "too small" in str(exc_info.value).lower()


# TEST 10: Multi-scene project where first route returns 410 (invalidated once, subsequent scenes use new route)
def test_multi_scene_410_invalidates_once_and_subsequent_scenes_use_working_route(tmp_path: Path):
    HuggingFaceImageRouter._deprecated_routes.clear()
    router = HuggingFaceImageRouter(
        api_keys=["hf_test_token"],
        preferred_models=["deprecated_model", "working_model"],
        providers=["auto"],
    )

    call_records = []

    def fake_call(prompt, model, provider, api_key, **kwargs):
        call_records.append(model)
        if model == "deprecated_model":
            exc = RuntimeError("HTTP 410: The requested model is deprecated and no longer supported by provider hf-inference")
            exc.response = MagicMock(status_code=410)
            raise exc
        return _create_dummy_image(1080, 1920)

    router._call_inference_client = fake_call

    # Create 5-scene plan
    scenes = [
        ScenePlan(i, float(i - 1), float(i), [SceneBeat(float(i - 1), float(i), "Action")], f"Prompt scene {i}")
        for i in range(1, 6)
    ]
    plan = ProjectPlan(5, "Test Multi Scene", scenes, {}, {})

    generated_paths = generate_images(
        plan,
        tmp_path,
        router=router,
        allow_placeholders=False,
    )

    assert len(generated_paths) == 5
    for p in generated_paths:
        assert p.is_file()

    # The deprecated model was called EXACTLY ONCE on Scene 1, then immediately invalidated
    assert call_records.count("deprecated_model") == 1
    # Working model was called for Scene 1 (fallback) and Scenes 2, 3, 4, 5
    assert call_records.count("working_model") == 5
    # Total calls = 1 (deprecated on scene 1) + 1 (working on scene 1) + 4 (scenes 2..5) = 6
    assert len(call_records) == 6


# TEST 11: Reference Style DNA is passed into image generation
def test_reference_style_dna_injected_into_prompts():
    beat = SceneBeat(0.0, 5.0, "Examining ground for clues", "macro push")
    scene = ScenePlan(1, 0.0, 5.0, [beat], "A detective examining footprints")
    plan = ProjectPlan(
        5,
        "Detective Story",
        [scene],
        style={
            "visual_style": {
                "description": "Neo-noir shadow cinema",
                "color_palette": "Deep amber and wet asphalt black",
                "lighting": "Low-key chiaroscuro with Venetian blind shadows",
                "camera_language": "Dutch angle tight macro",
            }
        },
        character={},
    )

    prompt = _format_scene_prompt(scene, plan)

    assert "Neo-noir shadow cinema" in prompt
    assert "Deep amber and wet asphalt black" in prompt
    assert "Low-key chiaroscuro with Venetian blind shadows" in prompt
    assert "Dutch angle tight macro" in prompt
    assert "vertical 9:16" in prompt


# TEST 12: 9:16 vertical shorts validation and geometry formatting
def test_vertical_9_16_shorts_validation(tmp_path: Path):
    # Test square source image (e.g. 1024x1024)
    square_img = Image.new("RGB", (1024, 1024), (200, 50, 50))
    fitted = ensure_vertical_shorts_dimensions(square_img, (1080, 1920))

    assert fitted.size == (1080, 1920)

    out_file = tmp_path / "fitted.jpg"
    fitted.save(out_file, format="JPEG")
    w, h = validate_image_file(out_file)
    assert (w, h) == (1080, 1920)
