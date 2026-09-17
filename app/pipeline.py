from __future__ import annotations
import json, re, shutil, subprocess
from datetime import datetime
from pathlib import Path
from .providers import gemini_text, hf_text_to_image
from .storage import load_config
from core.duration import validate_duration
from core.qc.engine import validate_output

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"
OUTPUT = ROOT / "output"
PROJECTS.mkdir(exist_ok=True); OUTPUT.mkdir(exist_ok=True)


def _fallback_plan(instruction: str, duration: int) -> list[dict]:
    count = max(1, min(18, (duration + 9) // 10))
    base = duration / count
    return [{"duration": round(base if i < count - 1 else duration - base * (count - 1), 3), "visual_prompt": f"Original cinematic vertical scene for {instruction}; consistent character, environment and objects; physically continuous action; no text; no dialogue", "motion": "subtle camera/parallax movement", "ambience": "natural environmental ambience", "sfx": [], "mood": "cinematic"} for i in range(count)]


def make_plan(instruction: str, duration: int) -> list[dict]:
    cfg = load_config()
    profile = json.dumps(cfg.get("reference_profile", {}), ensure_ascii=False)[:16000]
    prompt = f"""Create an original silent cinematic YouTube Short production plan for exactly {duration} seconds. User instruction: {instruction}\nReference production DNA: {profile}\nReturn ONLY JSON array. Use 3-5 meaningful visual beats per scene, physically continuous object actions, consistent character/environment, natural human vocal reactions only when useful, environmental ASMR and synchronized SFX. No spoken dialogue, no subtitles, no shot-for-shot copying."""
    try:
        text = gemini_text(prompt)
        match = re.search(r"\[.*\]", text, re.S)
        if match:
            plan = json.loads(match.group(0))
            if plan and all(float(x.get("duration", 0)) > 0 for x in plan):
                total = sum(float(x["duration"]) for x in plan)
                scale = duration / total
                for item in plan: item["duration"] = round(float(item["duration"]) * scale, 3)
                return plan
    except Exception:
        pass
    return _fallback_plan(instruction, duration)


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
        subprocess.run([ffmpeg,"-y","-loop","1","-i",str(image),"-t",f"{duration:.3f}","-vf",vf,"-an","-c:v","libx264","-preset","veryfast","-crf","23",str(out)],check=True,capture_output=True)
        result.append(out)
    return result


def render(clips: list[Path], project_dir: Path, duration: int) -> Path:
    ffmpeg=shutil.which("ffmpeg")
    if not ffmpeg: raise RuntimeError("FFmpeg is required")
    concat=project_dir/"concat.txt"
    concat.write_text("\n".join(f"file '{p.as_posix()}'" for p in clips), encoding="utf-8")
    out=OUTPUT/(project_dir.name+".mp4")
    subprocess.run([ffmpeg,"-y","-f","concat","-safe","0","-i",str(concat),"-t",str(duration),"-vf","scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2","-r","24","-pix_fmt","yuv420p","-movflags","+faststart",str(out)],check=True,capture_output=True)
    errors = validate_output(out, duration)
    if errors: raise RuntimeError("Output QC failed: " + "; ".join(errors))
    return out


def run_project(instruction: str, duration: int, status_cb=lambda s: None) -> Path:
    duration = validate_duration(duration)
    project_dir=PROJECTS/("short_"+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    project_dir.mkdir(parents=True)
    status_cb("Planning story and scenes...")
    plan=make_plan(instruction,duration)
    (project_dir/"plan.json").write_text(json.dumps({"duration": duration, "scenes": plan},ensure_ascii=False,indent=2),encoding="utf-8")
    status_cb("Generating images...")
    images=generate_images(plan,project_dir)
    status_cb("Animating images...")
    clips=animate_images(images,plan,project_dir)
    status_cb("Rendering and validating final video...")
    return render(clips,project_dir,duration)
