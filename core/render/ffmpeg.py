from __future__ import annotations
import shutil
import subprocess
from pathlib import Path
from core.audio.asmr import synthesize_rich_asmr_audio
from core.audio.timeline import AudioTimeline
from core.render.animation import animate_scene_image
from core.render.transitions import concat_clips, concat_with_transitions


def ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("FFmpeg is required and must be available on PATH")
    return path


def animate_image(
    image: Path,
    output: Path,
    duration: float,
    fps: int = 60,
    motion_type: str | None = None,
) -> Path:
    """Animate image into a smooth, high-FPS cinematic vertical video clip."""
    return animate_scene_image(
        image=image,
        output=output,
        duration=duration,
        fps=fps,
        motion_type=motion_type,
    )


def concat(
    clips: list[Path],
    output: Path,
    transition_type: str = "cut",
    transition_duration: float = 0.15,
) -> Path:
    """Concatenate video clips with natural transitions."""
    return concat_with_transitions(
        clips=clips,
        output=output,
        transition_type=transition_type,
        transition_duration=transition_duration,
    )


def synthesize_audio(duration: float, timeline: AudioTimeline, output: Path) -> Path:
    """Create a rich multi-layered ASMR/SFX bed with action-synced Foley events."""
    return synthesize_rich_asmr_audio(duration=duration, timeline=timeline, output=output)


def mux_video_audio(video: Path, audio: Path, output: Path, duration: float) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg(),
            "-y",
            "-i",
            str(video),
            "-i",
            str(audio),
            "-t",
            f"{duration:.3f}",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output),
        ],
        capture_output=True,
        check=True,
    )
    return output
