from __future__ import annotations

import io
from pathlib import Path
from PIL import Image, ImageOps


class ImageValidationError(ValueError):
    """Raised when an image fails decoding, dimension, or integrity checks."""
    pass


def validate_image_bytes(data: bytes, min_bytes: int = 512) -> Image.Image:
    """Validate raw image bytes and return the decoded PIL Image object."""
    if not data:
        raise ImageValidationError("Image data is empty")

    # Check for text/HTML/JSON error payloads mistakenly treated as image
    stripped = data[:200].strip()
    if stripped.startswith((b"{", b"[", b"<html", b"<!DOCTYPE", b"Error:", b"404", b"500", b"410")):
        snippet = data[:120].decode("utf-8", errors="replace").replace("\n", " ")
        raise ImageValidationError(f"Received text/HTML error payload instead of valid image data: {snippet}")

    if len(data) < min_bytes:
        raise ImageValidationError(f"Image data too small ({len(data)} bytes, minimum required: {min_bytes})")

    try:
        img = Image.open(io.BytesIO(data))
        img.verify()  # Verify header and integrity
    except Exception as exc:
        raise ImageValidationError(f"Corrupted image header or unreadable format: {exc}") from exc

    # Re-open for operational decoding (since verify() invalidates the PIL object)
    try:
        img = Image.open(io.BytesIO(data))
        img.load()  # Decode actual pixel buffers
    except Exception as exc:
        raise ImageValidationError(f"Failed to decode image pixels: {exc}") from exc

    if img.width <= 0 or img.height <= 0:
        raise ImageValidationError(f"Invalid image dimensions: {img.width}x{img.height}")

    return img


def validate_image_file(path: Path | str, min_bytes: int = 512) -> tuple[int, int]:
    """Verify that the target image file exists, is readable, decodable, and non-empty.
    Returns (width, height).
    """
    p = Path(path)
    if not p.is_file():
        raise ImageValidationError(f"Image file does not exist: {p}")

    size = p.stat().st_size
    if size < min_bytes:
        raise ImageValidationError(f"Image file size is too small ({size} bytes, min: {min_bytes}): {p}")

    data = p.read_bytes()
    img = validate_image_bytes(data, min_bytes=min_bytes)
    return img.width, img.height


def ensure_vertical_shorts_dimensions(
    img: Image.Image,
    target_size: tuple[int, int] = (1080, 1920)
) -> Image.Image:
    """Ensure the image exactly matches the 9:16 vertical shorts dimensions (default 1080x1920)
    using high-quality proportional fill and center-crop without stretching or distortion.
    """
    if img.size == target_size:
        return img
    
    # Use ImageOps.fit to perform proportional scale & center crop
    return ImageOps.fit(
        img.convert("RGB"),
        target_size,
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5)
    )
