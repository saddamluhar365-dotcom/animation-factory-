from __future__ import annotations
import shutil
import subprocess
from pathlib import Path


class CameraMotionProfile:
    MACRO_PUSH_IN = "macro_push_in"
    CINEMATIC_DRIFT = "cinematic_drift"
    DYNAMIC_TILT = "dynamic_tilt"
    REVEAL_PULL_OUT = "reveal_pull_out"
    PARALLAX_SHIMMER = "parallax_shimmer"


def select_motion_profile(scene_index: int, total_scenes: int, beat_action: str = "") -> str:
    """Assign a cinematic camera movement matching the scene role and reference rhythm."""
    action = beat_action.lower()
    if scene_index == 1:
        return CameraMotionProfile.MACRO_PUSH_IN
    if scene_index == total_scenes:
        return CameraMotionProfile.REVEAL_PULL_OUT
    if any(k in action for k in ("pour", "sizzle", "fry", "bubble", "sear", "flame")):
        return CameraMotionProfile.MACRO_PUSH_IN
    if any(k in action for k in ("chop", "slice", "cut", "prep", "dice")):
        return CameraMotionProfile.DYNAMIC_TILT
    if any(k in action for k in ("mix", "stir", "spread", "knead")):
        return CameraMotionProfile.PARALLAX_SHIMMER

    profiles = [
        CameraMotionProfile.CINEMATIC_DRIFT,
        CameraMotionProfile.DYNAMIC_TILT,
        CameraMotionProfile.MACRO_PUSH_IN,
        CameraMotionProfile.PARALLAX_SHIMMER,
    ]
    return profiles[(scene_index - 1) % len(profiles)]


def build_zoompan_filter(
    motion_type: str,
    duration: float,
    fps: int = 60,
    width: int = 1080,
    height: int = 1920,
) -> str:
    """Generate smooth, non-linear easing camera motion expressions in ffmpeg zoompan."""
    frames = max(1, round(duration * fps))
    n = max(1, frames)

    if motion_type == CameraMotionProfile.MACRO_PUSH_IN:
        # Smooth cubic ease-in push towards the focal point
        z_expr = f"min(1.0+0.16*(3*pow(on/{n},2)-2*pow(on/{n},3)),1.18)"
        x_expr = "(iw-iw/zoom)*0.5"
        y_expr = f"(ih-ih/zoom)*(0.5+0.06*sin(3.14159*on/{n}))"
    elif motion_type == CameraMotionProfile.CINEMATIC_DRIFT:
        # Smooth horizontal lateral tracking across culinary action
        z_expr = "1.08"
        x_expr = f"(iw-iw/zoom)*(0.35+0.30*(on/{n}))"
        y_expr = "(ih-ih/zoom)*0.5"
    elif motion_type == CameraMotionProfile.DYNAMIC_TILT:
        # Downward vertical tilt focusing on tactile interactions
        z_expr = "1.10"
        x_expr = "(iw-iw/zoom)*0.5"
        y_expr = f"(ih-ih/zoom)*(0.30+0.40*(3*pow(on/{n},2)-2*pow(on/{n},3)))"
    elif motion_type == CameraMotionProfile.REVEAL_PULL_OUT:
        # Smooth pull-back reveal of the finished dish
        z_expr = f"max(1.0,1.18-0.18*(3*pow(on/{n},2)-2*pow(on/{n},3)))"
        x_expr = "(iw-iw/zoom)*0.5"
        y_expr = "(ih-ih/zoom)*0.5"
    elif motion_type == CameraMotionProfile.PARALLAX_SHIMMER:
        # Gentle multi-axis breathing motion simulating stabilized handheld cinema camera
        z_expr = f"1.06+0.04*sin(2*3.14159*on/{n})"
        x_expr = f"(iw-iw/zoom)*(0.5+0.12*sin(3.14159*on/{n}))"
        y_expr = f"(ih-ih/zoom)*(0.5+0.10*cos(3.14159*on/{n}))"
    else:
        # Default smooth push-in
        z_expr = f"min(1.0+0.12*(on/{n}),1.14)"
        x_expr = "(iw-iw/zoom)*0.5"
        y_expr = "(ih-ih/zoom)*0.5"

    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d=1:s={width}x{height}:fps={fps},"
        f"format=yuv420p"
    )
    return vf


def animate_scene_image(
    image: Path,
    output: Path,
    duration: float,
    fps: int = 60,
    motion_type: str | None = None,
    width: int = 1080,
    height: int = 1920,
) -> Path:
    """Animate a static image into a high-FPS, cinematic vertical camera clip."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise RuntimeError("FFmpeg is required and must be available on PATH")

    output.parent.mkdir(parents=True, exist_ok=True)
    motion = motion_type or CameraMotionProfile.MACRO_PUSH_IN
    vf = build_zoompan_filter(motion, duration, fps=fps, width=width, height=height)

    subprocess.run(
        [
            ffmpeg_bin,
            "-y",
            "-loop",
            "1",
            "-i",
            str(image),
            "-t",
            f"{duration:.3f}",
            "-vf",
            vf,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "21",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ],
        capture_output=True,
        check=True,
    )
    return output
