from __future__ import annotations
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

from .providers import gemini_text, hf_text_to_image, tavily_search
from .storage import load_config
from core.audio.timeline import AudioEvent, AudioTimeline
from core.cleanup import cleanup_project_artifacts
from core.continuity.validator import validate_plan_continuity
from core.contracts import ProjectPlan, SceneBeat, ScenePlan
from core.db.memory import MemoryDB
from core.duration import distribute_duration, scene_count, validate_duration
from core.qc.engine import validate_output
from core.recovery.checkpoints import Checkpoints
from core.render.ffmpeg import animate_image, concat, mux_video_audio, synthesize_audio

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"
OUTPUT = ROOT / "output"
PROJECTS.mkdir(exist_ok=True)
OUTPUT.mkdir(exist_ok=True)


def _fallback_plan(instruction: str, duration: int) -> ProjectPlan:
    count = scene_count(duration)
    durations = distribute_duration(duration, count)
    scenes, cursor = [], 0.0
    for i, span in enumerate(durations, 1):
        end = cursor + span
        beats = []
        for b in range(4):
            bs = cursor + span * b / 4
            be = cursor + span * (b + 1) / 4
            action = ["establish the setting", "character makes a natural physical move", "object action continues through contact", "hold on the emotional visual reveal"][b]
            beats.append(SceneBeat(round(bs, 3), round(be, 3), action, "slow cinematic push and gentle parallax"))
        scenes.append(ScenePlan(i, round(cursor, 3), round(end, 3), beats, f"Original cinematic vertical scene for {instruction}; preserve character face, clothes, body proportions, object identity and environment; every object interaction must be physically continuous; no text, subtitles, logos, watermark or spoken dialogue."))
        cursor = end
    return ProjectPlan(duration, instruction[:80], scenes, load_config().get("reference_profile", {}), {})


def _extract_json(text: str):
    match = re.search(r"\[[\s\S]*\]", text or "")
    return json.loads(match.group(0)) if match else None


def _normalize_gemini_plan(raw: list[dict], instruction: str, duration: int) -> ProjectPlan:
    count = scene_count(duration)
    durations = distribute_duration(duration, min(max(1, len(raw)), count))
    raw = raw[:len(durations)]
    if len(raw) < len(durations):
        return _fallback_plan(instruction, duration)
    scenes, cursor = [], 0.0
    for i, (item, span) in enumerate(zip(raw, durations), 1):
        end = cursor + span
        actions = item.get("beats") or item.get("visual_beats") or []
        actions = [str(x.get("action", x) if isinstance(x, dict) else x) for x in actions][:5]
        while len(actions) < 3:
            actions.append("continue the same physical action with consistent objects")
        actions = actions[:5]
        beats = [SceneBeat(round(cursor + span*j/len(actions), 3), round(cursor + span*(j+1)/len(actions), 3), a, str(item.get("camera", "gentle cinematic movement"))) for j, a in enumerate(actions)]
        prompt = str(item.get("visual_prompt") or item.get("prompt") or instruction)
        prompt += ", original production, physically continuous object interactions, consistent character and environment, no dialogue, no subtitles, no text"
        scenes.append(ScenePlan(i, round(cursor, 3), round(end, 3), beats, prompt, item.get("audio_events", []), {"objects_must_persist": True, "no_teleportation": True}))
        cursor = end
    return ProjectPlan(duration, str(raw[0].get("title", instruction[:80])), scenes, load_config().get("reference_profile", {}), {})


def make_plan(instruction: str, duration: int, research: list[dict] | None = None) -> ProjectPlan:
    duration = validate_duration(duration)
    cfg = load_config()
    profile = json.dumps(cfg.get("reference_profile", {}), ensure_ascii=False)[:16000]
    research_text = json.dumps(research or [], ensure_ascii=False)[:12000]
    prompt = f"""Create an ORIGINAL silent cinematic YouTube Short plan for exactly {duration} seconds. User request: {instruction}\nReference production DNA (high-level only): {profile}\nVerified research context: {research_text}\nReturn ONLY a JSON array of scenes. Each scene must contain visual_prompt, camera, beats (3-5 short physical actions), and audio_events. No spoken dialogue. Use natural human vocal reactions only as non-verbal expression events. Include environmental ASMR/SFX with timestamps. Every pickup, placement, carrying, opening, closing, pouring, cutting, mixing or lifting action must be physically continuous: objects cannot teleport, disappear, duplicate, float, morph, or change identity. Do not copy characters, dialogue, scenes or shot sequences from references."""
    try:
        parsed = _extract_json(gemini_text(prompt))
        if isinstance(parsed, list) and parsed:
            plan = _normalize_gemini_plan(parsed, instruction, duration)
            if not validate_plan_continuity(plan):
                return plan
    except Exception:
        pass
    return _fallback_plan(instruction, duration)


def _fallback_image(path: Path, scene_index: int, instruction: str) -> Path:
    img = Image.new("RGB", (1080, 1920), (232, 224, 210))
    draw = ImageDraw.Draw(img)
    draw.ellipse((180, 250, 900, 970), outline=(80, 70, 60), width=10)
    draw.rectangle((250, 1050, 830, 1600), outline=(90, 80, 70), width=10)
    img.save(path, quality=92)
    return path


def generate_images(plan: ProjectPlan, project_dir: Path, status_cb=lambda s: None) -> list[Path]:
    image_dir = project_dir / "images"
    image_dir.mkdir(exist_ok=True)
    result = []
    for scene in plan.scenes:
        prompt = scene.visual_prompt + ", vertical 9:16, cinematic, high detail, coherent lighting, no text, no watermark"
        path = image_dir / f"scene_{scene.index:03d}.jpg"
        try:
            data = hf_text_to_image(prompt)
            if not data.startswith(b"\xff\xd8") and not data.startswith(b"\x89PNG"):
                raise RuntimeError("image provider returned non-image data")
            path.write_bytes(data)
        except Exception as exc:
            status_cb(f"Scene {scene.index}: image API failed, using local placeholder ({exc})")
            _fallback_image(path, scene.index, plan.title)
        result.append(path)
    return result


def build_audio_timeline(plan: ProjectPlan) -> AudioTimeline:
    timeline = AudioTimeline(plan.duration)
    for scene in plan.scenes:
        timeline.add(AudioEvent(scene.start, min(scene.end, scene.start + min(0.8, scene.end-scene.start)), "ambience", "environment", 0.25))
        for beat in scene.beats:
            lower = beat.action.lower()
            if any(word in lower for word in ("cut", "place", "pour", "tap", "step", "knock", "mix", "open", "close")):
                timeline.add(AudioEvent(beat.start, min(beat.end, beat.start + 0.35), "sfx", "tap", 0.18, True))
    return timeline


def animate_images(images: list[Path], plan: ProjectPlan, project_dir: Path) -> list[Path]:
    clips = project_dir / "clips"
    clips.mkdir(exist_ok=True)
    result = []
    for image, scene in zip(images, plan.scenes):
        result.append(animate_image(image, clips / f"scene_{scene.index:03d}.mp4", scene.end - scene.start))
    return result


def render(clips: list[Path], plan: ProjectPlan, project_dir: Path) -> tuple[Path, AudioTimeline, list[str]]:
    silent = project_dir / "video_silent.mp4"
    concat(clips, silent)
    timeline = build_audio_timeline(plan)
    timeline_errors = timeline.validate()
    if timeline_errors:
        raise RuntimeError("Audio timeline invalid: " + "; ".join(timeline_errors))
    audio = project_dir / "audio.wav.m4a"
    synthesize_audio(plan.duration, timeline, audio)
    out = OUTPUT / f"{project_dir.name}.mp4"
    mux_video_audio(silent, audio, out, plan.duration)
    errors = validate_output(out, plan.duration)
    if errors:
        raise RuntimeError("Output QC failed: " + "; ".join(errors))
    (project_dir / "audio_timeline.json").write_text(json.dumps(timeline.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return out, timeline, errors


def run_project(instruction: str, duration: int, status_cb=lambda s: None) -> Path:
    duration = validate_duration(duration)
    project_dir = PROJECTS / ("short_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f"))
    project_dir.mkdir(parents=True)
    project_key = project_dir.name
    db = MemoryDB()
    db.remember_project(project_key, instruction, duration, "created")
    db.remember("instruction", {"instruction": instruction, "duration": duration}, project_key, "latest")
    checkpoint = Checkpoints(project_dir / "checkpoint.json")
    checkpoint.save("created", {"duration": duration, "instruction": instruction})
    db.remember_checkpoint(project_key, "created", {"duration": duration, "instruction": instruction})
    try:
        status_cb("Researching the requested topic...")
        research = tavily_search(instruction)
        for item in research:
            db.remember_research({"url": item.get("url"), "title": item.get("title"), "topic": instruction, "summary": item.get("content") or item.get("snippet"), "evidence": item})
        db.remember("research_batch", {"query": instruction, "count": len(research), "retrieved_at": datetime.now(timezone.utc).isoformat()}, project_key, "latest")
        db.remember_decision(project_key, {"key": "research", "provider": "tavily", "result_count": len(research), "fallback": not bool(research)})

        status_cb("Planning story, scenes and synchronized audio...")
        plan = make_plan(instruction, duration, research)
        plan_data = plan.to_dict()
        continuity_errors = validate_plan_continuity(plan)
        if continuity_errors:
            raise RuntimeError("Plan continuity failed: " + "; ".join(continuity_errors))
        (project_dir / "plan.json").write_text(json.dumps(plan_data, ensure_ascii=False, indent=2), encoding="utf-8")
        db.remember_plan(project_key, plan_data)
        db.remember_project(project_key, instruction, duration, "planned")
        db.remember_checkpoint(project_key, "planned")
        checkpoint.save("planned")

        status_cb("Generating consistent scene images...")
        images = generate_images(plan, project_dir, status_cb)
        db.remember("image_generation", {"count": len(images), "scenes": [str(p) for p in images]}, project_key, "latest")
        for image in images:
            db.remember_artifact(project_key, "image", str(image), {"temporary": True})
        checkpoint.save("images", {"count": len(images)})
        db.remember_checkpoint(project_key, "images", {"count": len(images)})

        status_cb("Animating scenes locally with FFmpeg...")
        clips = animate_images(images, plan, project_dir)
        db.remember("animation", {"count": len(clips), "clips": [str(p) for p in clips]}, project_key, "latest")
        for clip in clips:
            db.remember_artifact(project_key, "clip", str(clip), {"temporary": True})
        checkpoint.save("animated", {"count": len(clips)})
        db.remember_checkpoint(project_key, "animated", {"count": len(clips)})

        status_cb("Mixing ASMR/SFX and rendering final MP4...")
        out, timeline, _ = render(clips, plan, project_dir)
        db.remember("audio_timeline", timeline.to_dict(), project_key, "latest")
        db.remember_artifact(project_key, "final_video", str(out), {"temporary": False})
        db.remember_qc(project_key, [], str(out))
        db.remember_project(project_key, instruction, duration, "completed")
        checkpoint.save("completed", {"output": str(out)})
        db.remember_checkpoint(project_key, "completed", {"output": str(out)})
        status_cb("Cleaning temporary images, audio and intermediate files...")
        cleanup_project_artifacts(project_dir, out, OUTPUT)
        db.remember("cleanup", {"project_dir": str(project_dir), "final_output": str(out), "temporary_artifacts_deleted": True}, project_key, "completed")
        status_cb(f"QC PASS — {out}")
        return out
    except Exception as exc:
        db.remember_error(project_key, "pipeline", exc)
        db.remember_project(project_key, instruction, duration, "failed")
        try:
            db.remember_qc(project_key, [str(exc)])
        except Exception:
            pass
        raise
