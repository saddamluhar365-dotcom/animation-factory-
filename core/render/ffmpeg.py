from __future__ import annotations
import shutil
import subprocess
from pathlib import Path
from core.audio.timeline import AudioTimeline


def ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("FFmpeg is required and must be available on PATH")
    return path


def animate_image(image: Path, output: Path, duration: float, fps: int = 24) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,zoompan=z='min(zoom+0.0008,1.08)':d=1:s=1080x1920:fps=%d,format=yuv420p" % fps
    subprocess.run([ffmpeg(), "-y", "-loop", "1", "-i", str(image), "-t", f"{duration:.3f}", "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)], capture_output=True, check=True)
    return output


def concat(clips: list[Path], output: Path) -> Path:
    if not clips:
        raise ValueError("No clips to render")
    manifest = output.with_suffix(".concat.txt")
    manifest.write_text("\n".join(f"file '{p.resolve().as_posix().replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'" for p in clips), encoding="utf-8")
    subprocess.run([ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c", "copy", "-movflags", "+faststart", str(output)], capture_output=True, check=True)
    return output


def synthesize_audio(duration: float, timeline: AudioTimeline, output: Path) -> Path:
    """Create a quiet local ambience/SFX bed; no spoken dialogue is synthesized."""
    output.parent.mkdir(parents=True, exist_ok=True)
    filters = [f"anoisesrc=d={duration:.3f}:c=brown:r=48000:a=0.018,highpass=f=90,lowpass=f=8000[amb]"]
    labels = ["[amb]"]
    idx = 0
    for event in timeline.events:
        if event.kind not in {"sfx", "expression"}:
            continue
        length = max(0.04, min(1.0, event.end - event.start))
        freq = 520 if event.name in {"tap", "step", "knock"} else 260
        label = f"e{idx}"
        filters.append(f"sine=f={freq}:d={length:.3f}:r=48000,afade=t=out:st={max(0,length-0.12):.3f}:d=0.12,volume={min(event.volume,0.25):.3f},adelay={int(event.start*1000)}|{int(event.start*1000)}[{label}]")
        labels.append(f"[{label}]")
        idx += 1
    if len(labels) == 1:
        filters.append(f"[amb]volume=0.65[aout]")
    else:
        filters.append("".join(labels) + f"amix=inputs={len(labels)}:duration=longest:dropout_transition=0,alimiter=limit=0.85[aout]")
    graph = ";".join(filters)
    subprocess.run([ffmpeg(), "-y", "-filter_complex", graph, "-map", "[aout]", "-t", f"{duration:.3f}", "-ar", "48000", "-ac", "2", "-c:a", "aac", "-b:a", "128k", str(output)], capture_output=True, check=True)
    return output


def mux_video_audio(video: Path, audio: Path, output: Path, duration: float) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg(), "-y", "-i", str(video), "-i", str(audio), "-t", f"{duration:.3f}", "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-shortest", "-movflags", "+faststart", str(output)], capture_output=True, check=True)
    return output
