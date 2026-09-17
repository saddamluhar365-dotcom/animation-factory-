from __future__ import annotations
import shutil, subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent


def mix_background_audio(video: Path, project_dir: Path, music: Path|None=None, ambience: Path|None=None, sfx: list[Path]|None=None) -> Path:
    """Mix optional local licensed audio assets into a rendered video.
    No audio asset is downloaded automatically; users control the licensed sources.
    """
    ffmpeg=shutil.which("ffmpeg")
    if not ffmpeg: raise RuntimeError("FFmpeg is required")
    inputs=[str(video)]; filters=[]; labels=[]
    for p in [music, ambience, *(sfx or [])]:
        if p and p.exists(): inputs += [str(p)]
    if len(inputs)==1: return video
    args=[ffmpeg,"-y"]
    for p in inputs: args += ["-i",p]
    n=len(inputs)-1
    streams=["1:a" if i==0 else f"{i+1}:a" for i in range(n)]
    filters.append("[0:v]null[v]")
    for idx,s in enumerate(streams,1): filters.append(f"[{s}]volume=0.18[a{idx}]")
    mix="".join(f"[a{i}]" for i in range(1,n+1))+f"amix=inputs={n}:duration=first:dropout_transition=2[a]"
    filters.append(mix)
    out=project_dir/"final_audio.mp4"
    args += ["-filter_complex",";".join(filters),"-map","[v]","-map","[a]","-c:v","copy","-c:a","aac","-b:a","160k",str(out)]
    subprocess.run(args,check=True,capture_output=True)
    return out
