from __future__ import annotations
import json, re, shutil, subprocess
from pathlib import Path
from .providers import gemini_text, hf_text_to_image
from .storage import load_config

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"
OUTPUT = ROOT / "output"
PROJECTS.mkdir(exist_ok=True); OUTPUT.mkdir(exist_ok=True)


def make_plan(instruction: str, duration: int) -> list[dict]:
    cfg = load_config()
    profile = json.dumps(cfg.get("reference_profile", {}), ensure_ascii=False)[:12000]
    prompt = f"""Create an original silent cinematic short production plan. Target duration: {duration} seconds. User instruction: {instruction}\nReference style profile: {profile}\nReturn ONLY JSON array. Each item must contain duration, visual_prompt, motion, ambience, sfx, mood. No dialogue. Use natural character vocal reactions only when useful. Keep actions physically continuous and objects consistent."""
    text = gemini_text(prompt)
    match = re.search(r"\[.*\]", text, re.S)
    if not match:
        raise RuntimeError("Planner did not return JSON")
    plan = json.loads(match.group(0))
    return plan


def generate_images(plan: list[dict], project_dir: Path) -> list[Path]:
    image_dir = project_dir / "images"; image_dir.mkdir(exist_ok=True)
    result = []
    for i, scene in enumerate(plan, 1):
        prompt = scene["visual_prompt"] + ", vertical 9:16 cinematic illustration, consistent character and environment, no text, no watermark"
        data = hf_text_to_image(prompt)
        path = image_dir / f"scene_{i:03d}.jpg"
        path.write_bytes(data)
        result.append(path)
    return result


def animate_images(images: list[Path], plan: list[dict], project_dir: Path) -> list[Path]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg: raise RuntimeError("FFmpeg is required")
    clips = project_dir / "clips"; clips.mkdir(exist_ok=True)
    result=[]
    for i, image in enumerate(images):
        duration=float(plan[i].get("duration",5))
        out=clips/f"scene_{i+1:03d}.mp4"
        vf="scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,zoompan=z='min(zoom+0.0008,1.08)':d=1:s=1080x1920:fps=24,format=yuv420p"
        subprocess.run([ffmpeg,"-y","-loop","1","-i",str(image),"-t",str(duration),"-vf",vf,"-an","-c:v","libx264","-preset","veryfast","-crf","23",str(out)],check=True,capture_output=True)
        result.append(out)
    return result


def render(clips: list[Path], project_dir: Path) -> Path:
    ffmpeg=shutil.which("ffmpeg")
    if not ffmpeg: raise RuntimeError("FFmpeg is required")
    concat=project_dir/"concat.txt"
    concat.write_text("\n".join(f"file '{p.as_posix()}'" for p in clips), encoding="utf-8")
    out=OUTPUT/(project_dir.name+".mp4")
    subprocess.run([ffmpeg,"-y","-f","concat","-safe","0","-i",str(concat),"-c","copy","-movflags","+faststart",str(out)],check=True,capture_output=True)
    return out


def run_project(instruction: str, duration: int, status_cb=lambda s: None) -> Path:
    if not 1 <= duration <= 180: raise ValueError("Duration must be 1-180 seconds")
    project_dir=PROJECTS/("short_"+__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S'))
    project_dir.mkdir(parents=True)
    status_cb("Planning story and scenes...")
    plan=make_plan(instruction,duration)
    (project_dir/"plan.json").write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding="utf-8")
    status_cb("Generating images...")
    images=generate_images(plan,project_dir)
    status_cb("Animating images...")
    clips=animate_images(images,plan,project_dir)
    status_cb("Rendering final video...")
    return render(clips,project_dir)
