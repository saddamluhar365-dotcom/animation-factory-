from __future__ import annotations

import io
import logging
import time
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw

from .contracts import ImageResult, ImageRouteStatus
from .validator import ensure_vertical_shorts_dimensions, validate_image_bytes

logger = logging.getLogger(__name__)

# Configurable list of modern, supported text-to-image models
PREFERRED_IMAGE_MODELS: list[str] = [
    "black-forest-labs/FLUX.1-schnell",
    "black-forest-labs/FLUX.1-dev",
    "stabilityai/stable-diffusion-3.5-large",
    "stabilityai/stable-diffusion-xl-base-1.0",
]

DEFAULT_IMAGE_PROVIDERS: list[str] = ["auto", "fal-ai", "nscale", "wavespeed", "replicate"]


class HuggingFaceImageRouter:
    """Manages model discovery, provider routing, multi-key rotation,
    and HTTP 410 deprecation recovery for text-to-image generation.
    """

    # Global tracking of permanently deprecated (model, provider) routes
    _deprecated_routes: set[tuple[str, str]] = set()

    def __init__(
        self,
        api_keys: list[str] | None = None,
        preferred_models: list[str] | None = None,
        providers: list[str] | None = None,
    ):
        self.api_keys = list(api_keys or [])
        self.preferred_models = list(preferred_models or PREFERRED_IMAGE_MODELS)
        self.providers = list(providers or DEFAULT_IMAGE_PROVIDERS)
        self.active_model: str | None = None
        self.active_provider: str | None = None
        self._key_index = 0

    def get_current_key(self) -> str:
        if not self.api_keys:
            raise RuntimeError("No Hugging Face API tokens configured")
        return self.api_keys[self._key_index % len(self.api_keys)]

    def rotate_key(self) -> str:
        if len(self.api_keys) > 1:
            self._key_index += 1
            logger.info("Rotated to Hugging Face API key index %d", self._key_index % len(self.api_keys))
        return self.get_current_key()

    def mark_route_deprecated(self, model: str, provider: str) -> None:
        self._deprecated_routes.add((model, provider))
        if self.active_model == model and self.active_provider == provider:
            self.active_model = None
            self.active_provider = None
        logger.warning("Marked image route (%s, %s) as deprecated/unavailable", model, provider)

    def is_route_available(self, model: str, provider: str) -> bool:
        return (model, provider) not in self._deprecated_routes

    def candidate_routes(self) -> list[tuple[str, str]]:
        routes: list[tuple[str, str]] = []
        # If there is an active successful route, test it first
        if self.active_model and self.active_provider:
            if self.is_route_available(self.active_model, self.active_provider):
                routes.append((self.active_model, self.active_provider))

        # Add all other combinations of preferred models and providers
        for model in self.preferred_models:
            for provider in self.providers:
                pair = (model, provider)
                if pair not in routes and self.is_route_available(model, provider):
                    routes.append(pair)
        return routes

    def _call_inference_client(
        self,
        prompt: str,
        model: str,
        provider: str,
        api_key: str,
        width: int = 1080,
        height: int = 1920,
        seed: int | None = None,
    ) -> Image.Image:
        """Invokes huggingface_hub.InferenceClient to generate image."""
        try:
            from huggingface_hub import InferenceClient
        except ImportError as exc:
            raise RuntimeError("huggingface_hub is not installed. Run pip install huggingface_hub") from exc

        # Use InferenceClient with the specified provider routing
        client = InferenceClient(api_key=api_key, provider=provider)
        
        kwargs: dict[str, Any] = {"model": model}
        if seed is not None:
            kwargs["seed"] = seed

        # Invoke text_to_image
        result = client.text_to_image(prompt, **kwargs)
        if isinstance(result, Image.Image):
            return result
        elif isinstance(result, (bytes, bytearray)):
            return validate_image_bytes(bytes(result))
        else:
            raise ValueError(f"Unexpected return type from text_to_image: {type(result)}")

    def generate(
        self,
        prompt: str,
        *,
        output_path: Path | str,
        width: int = 1080,
        height: int = 1920,
        seed: int | None = None,
        style: dict[str, Any] | None = None,
        project_context: str | None = None,
        allow_placeholders: bool = False,
    ) -> ImageResult:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        start_time = time.time()
        retries = 0
        last_error = "No Hugging Face token configured"

        if not self.api_keys:
            if allow_placeholders:
                return self._create_placeholder(out, prompt, "No token configured (dev mode)")
            raise RuntimeError(f"Hugging Face image generation failed: {last_error}")

        # Try available routes
        routes = self.candidate_routes()
        if not routes:
            if allow_placeholders:
                return self._create_placeholder(out, prompt, "All routes deprecated (dev mode)")
            raise RuntimeError("All candidate Hugging Face image routes are marked deprecated or unavailable")

        for model, provider in routes:
            # Try with current key, rotate on 429/quota if multiple keys exist
            attempts_for_route = 0
            max_attempts = max(1, len(self.api_keys))

            while attempts_for_route < max_attempts:
                attempts_for_route += 1
                key = self.get_current_key()
                try:
                    raw_img = self._call_inference_client(
                        prompt=prompt,
                        model=model,
                        provider=provider,
                        api_key=key,
                        width=width,
                        height=height,
                        seed=seed,
                    )
                    # Convert & ensure strict 9:16 vertical geometry
                    final_img = ensure_vertical_shorts_dimensions(raw_img, (width, height))
                    final_img.save(out, format="JPEG", quality=92)

                    # Mark route as active for subsequent scenes
                    self.active_model = model
                    self.active_provider = provider

                    duration = time.time() - start_time
                    route_desc = f"{provider}:{model}"
                    return ImageResult(
                        path=out,
                        model=model,
                        provider=provider,
                        metadata={
                            "width": final_img.width,
                            "height": final_img.height,
                            "prompt": prompt,
                            "seed": seed,
                            "project_context": project_context,
                        },
                        duration=duration,
                        retry_count=retries,
                        route_used=route_desc,
                    )

                except Exception as exc:
                    retries += 1
                    err_msg = str(exc)
                    status_code = getattr(getattr(exc, "response", None), "status_code", None)

                    # 1. Check for HTTP 410 (Model Deprecated / Unsupported by provider)
                    is_410 = (
                        status_code == 410
                        or "410" in err_msg
                        or "deprecated" in err_msg.lower()
                        or "no longer supported" in err_msg.lower()
                    )
                    if is_410:
                        self.mark_route_deprecated(model, provider)
                        last_error = f"HTTP 410: Model {model} is deprecated by provider {provider}"
                        # Break out of key attempts for this dead route and move to next candidate route immediately
                        break

                    # 2. Check for HTTP 429 or Quota Exhaustion
                    is_429 = status_code == 429 or "429" in err_msg or "rate limit" in err_msg.lower()
                    is_quota = "quota" in err_msg.lower() or "payment" in err_msg.lower()
                    if is_429 or is_quota:
                        last_error = f"HTTP {status_code or 429}: Rate limit / quota exhausted for key"
                        if len(self.api_keys) > 1 and attempts_for_route < max_attempts:
                            self.rotate_key()
                            continue
                        else:
                            # Break route loop if single key rate limited
                            break

                    # 3. Check for 401 / 403 (Invalid Token / Unauthorized)
                    is_auth = status_code in (401, 403) or "unauthorized" in err_msg.lower() or "invalid token" in err_msg.lower()
                    if is_auth:
                        last_error = f"Authentication failed: {err_msg[:200]}"
                        if len(self.api_keys) > 1 and attempts_for_route < max_attempts:
                            self.rotate_key()
                            continue
                        raise RuntimeError(f"Hugging Face authentication error: {last_error}")

                    # 4. Check for 503 / 500 / 502 / 504 (Temporary server / timeout)
                    is_temp = status_code in (500, 502, 503, 504) or "503" in err_msg or "timeout" in err_msg.lower()
                    if is_temp:
                        last_error = f"Temporary service error ({status_code or 503}): {err_msg[:200]}"
                        # Try next route or brief backoff
                        break

                    # Generic failure on this route
                    last_error = err_msg
                    break

        if allow_placeholders:
            logger.warning("All image generation routes failed; generating test placeholder: %s", last_error)
            return self._create_placeholder(out, prompt, last_error)

        raise RuntimeError(f"Hugging Face image generation failed across all routes: {last_error}")

    def _create_placeholder(self, path: Path, prompt: str, reason: str) -> ImageResult:
        """Deterministic placeholder for development/unit test fixtures only."""
        img = Image.new("RGB", (1080, 1920), (30, 35, 45))
        draw = ImageDraw.Draw(img)
        draw.ellipse((180, 350, 900, 1070), outline=(120, 140, 180), width=8)
        draw.rectangle((240, 1150, 840, 1700), outline=(100, 120, 160), width=8)
        img.save(path, format="JPEG", quality=90)
        return ImageResult(
            path=path,
            model="placeholder-fixture",
            provider="local",
            metadata={"placeholder": True, "reason": reason, "prompt": prompt},
            duration=0.01,
            retry_count=0,
            route_used="local:placeholder",
        )


def generate_image(
    prompt: str,
    *,
    output_path: Path | str,
    width: int = 1080,
    height: int = 1920,
    seed: int | None = None,
    style: dict[str, Any] | None = None,
    project_context: str | None = None,
    allow_placeholders: bool = False,
    router: HuggingFaceImageRouter | None = None,
    api_keys: list[str] | None = None,
) -> ImageResult:
    """Canonical entrypoint for generating an image behind the routing abstraction."""
    if router is None:
        router = HuggingFaceImageRouter(api_keys=api_keys)
    return router.generate(
        prompt=prompt,
        output_path=output_path,
        width=width,
        height=height,
        seed=seed,
        style=style,
        project_context=project_context,
        allow_placeholders=allow_placeholders,
    )
