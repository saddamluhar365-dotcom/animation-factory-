from __future__ import annotations
import logging
import shutil
import subprocess
import time
from pathlib import Path
from PIL import Image, ImageDraw

from .contracts import KeyHealthStatus, VideoGenerationRequest, VideoGenerationResult
from .pool import FalKeyPool, FalKeyRecord
from .client import FalHttpClient

logger = logging.getLogger(__name__)

# Dynamic candidate video models list (tested for high retention 9:16 vertical Shorts)
PREFERRED_FAL_VIDEO_MODELS = [
    "fal-ai/kling-video/v1/standard/text-to-video",
    "fal-ai/luma-dream-machine",
    "fal-ai/minimax/video-01",
    "fal-ai/hunyuan-video",
    "fal-ai/fast-svd/text-to-video",
]


class FalVideoRouter:
    """Manages model discovery, multi-key rotation, 429 handling, and failover for FAL video."""

    _deprecated_models: set[str] = set()

    def __init__(
        self,
        pool: FalKeyPool | None = None,
        api_keys: list[str | dict] | None = None,
        models: list[str] | None = None,
        client: FalHttpClient | None = None,
    ):
        if pool is not None:
            self.pool = pool
        else:
            self.pool = FalKeyPool(keys=api_keys)
        self.models = list(models or PREFERRED_FAL_VIDEO_MODELS)
        self.client = client or FalHttpClient()

    def candidate_models(self) -> list[str]:
        return [m for m in self.models if m not in self._deprecated_models]

    def mark_model_deprecated(self, model: str) -> None:
        self._deprecated_models.add(model)
        logger.warning("Marked FAL model %s as unavailable / deprecated", model)

    def generate(
        self,
        request: VideoGenerationRequest,
        output_path: Path,
        allow_placeholders: bool = False,
    ) -> VideoGenerationResult:
        """Execute video generation with multi-key rotation on 429 and model failover."""
        start_time = time.time()
        last_error = "No FAL models attempted"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        for model in self.candidate_models():
            # Try available keys for this model
            attempts = 0
            max_attempts = max(1, self.pool.count() * 2)

            while attempts < max_attempts:
                attempts += 1
                try:
                    key_rec = self.pool.get_next_key()
                except RuntimeError as exc:
                    last_error = str(exc)
                    break

                try:
                    logger.info("Attempting FAL video generation: model=%s key=%s", model, key_rec.masked)
                    resp = self.client.submit_job(
                        model=model,
                        prompt=request.prompt,
                        api_key=key_rec.raw_key,
                        duration=request.duration,
                        aspect_ratio=request.aspect_ratio,
                        seed=request.seed,
                    )

                    # HTTP 429: Rate Limit -> rotate key immediately
                    if resp.status_code == 429:
                        self.pool.mark_rate_limited(key_rec.raw_key)
                        last_error = f"HTTP 429 Rate Limit on key {key_rec.masked}"
                        continue

                    # HTTP 401 / 403: Invalid Key -> disable key and rotate
                    if resp.status_code in (401, 403):
                        self.pool.mark_invalid(key_rec.raw_key, reason=f"HTTP {resp.status_code}")
                        last_error = f"HTTP {resp.status_code} Authentication failure on key {key_rec.masked}"
                        continue

                    # HTTP 404 / 410: Model unavailable / deprecated -> break to next model
                    if resp.status_code in (404, 410):
                        self.mark_model_deprecated(model)
                        last_error = f"HTTP {resp.status_code} Model {model} unavailable"
                        break

                    if not resp.ok:
                        last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                        continue

                    # Parse response
                    job_data = resp.json()
                    # If synchronous response with video url:
                    video_url = None
                    if "video" in job_data and isinstance(job_data["video"], dict):
                        video_url = job_data["video"].get("url")
                    elif "request_id" in job_data:
                        result_data = self.client.poll_job(
                            model=model,
                            request_id=job_data["request_id"],
                            api_key=key_rec.raw_key,
                        )
                        if "video" in result_data and isinstance(result_data["video"], dict):
                            video_url = result_data["video"].get("url")

                    if not video_url:
                        last_error = f"FAL response missing video URL from model {model}"
                        continue

                    # Download video
                    self.client.download_video(video_url, output_path)
                    self._validate_generated_clip(output_path)
                    self.pool.mark_success(key_rec.raw_key)

                    latency = round(time.time() - start_time, 2)
                    return VideoGenerationResult(
                        video_path=output_path,
                        provider="fal_video",
                        model_used=model,
                        key_alias=key_rec.masked,
                        latency_seconds=latency,
                        status="success",
                        details={"duration": request.duration, "aspect_ratio": request.aspect_ratio},
                    )

                except Exception as exc:
                    last_error = str(exc)
                    logger.warning("FAL generation error (model=%s, key=%s): %s", model, key_rec.masked, exc)
                    continue

        # If all keys and models failed:
        if allow_placeholders:
            self._create_placeholder_clip(output_path, request.duration, request.prompt, last_error)
            return VideoGenerationResult(
                video_path=output_path,
                provider="fal_video",
                model_used="placeholder",
                key_alias="none",
                latency_seconds=round(time.time() - start_time, 2),
                status="placeholder",
                details={"fallback": True, "reason": last_error},
            )

        raise RuntimeError(
            f"FAL Video generation failed across all candidate models and API keys: {last_error}. "
            f"Please check your FAL keys in Settings -> APIs."
        )

    def _validate_generated_clip(self, path: Path) -> None:
        if not path.exists() or path.stat().st_size < 1024:
            raise ValueError(f"Generated video clip is missing or empty: {path}")

    def _create_placeholder_clip(self, output: Path, duration: float, prompt: str, error: str) -> Path:
        """Create a valid vertical MP4 fixture for testing/dev environments."""
        output.parent.mkdir(parents=True, exist_ok=True)
        img_path = output.with_suffix(".placeholder.jpg")
        img = Image.new("RGB", (1080, 1920), color=(30, 45, 60))
        draw = ImageDraw.Draw(img)
        draw.text((80, 300), "FAL VIDEO FIXTURE (DEV MODE)", fill=(255, 200, 50))
        draw.text((80, 360), f"Prompt: {prompt[:80]}...", fill=(220, 220, 220))
        draw.text((80, 420), f"Fallback: {error[:80]}", fill=(200, 100, 100))
        img.save(img_path)

        ffmpeg_bin = shutil.which("ffmpeg")
        if ffmpeg_bin:
            subprocess.run(
                [
                    ffmpeg_bin, "-y", "-loop", "1", "-i", str(img_path),
                    "-t", f"{duration:.3f}",
                    "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuv420p",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                    str(output),
                ],
                capture_output=True,
                check=True,
            )
        try:
            img_path.unlink()
        except OSError:
            pass
        return output
